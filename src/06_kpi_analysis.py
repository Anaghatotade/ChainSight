"""
Step 6 - KPI analysis: ABC, demand variability (XYZ), intermittency classes, price-cut uplift, and an
ASSUMPTION-labelled safety-stock view.

Real (measured): revenue, ABC class, weekly CV, zero-sales share, demand class, price-cut uplift.
Assumed (labelled): lead time, service level -> safety stock / reorder point (the M5 data has no inventory or lead times).

Reads  data/processed/*
Writes outputs/charts/kpi_*.png, outputs/tables/kpi_*.csv, adds numbers to outputs/tables/key_numbers.json

Run:  python src/06_kpi_analysis.py
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import analysis
import config as cfg
import keynums as nums
import kpis
import panel as pn
import viz


def main():
    cfg.ensure_dirs()
    viz.setup()
    panel = pn.load_panel()
    N = {}
    ov = kpis.build_overall_kpis(panel)
    pd.DataFrame([ov]).to_csv(cfg.TABLES / "kpi_overall.csv", index=False)
    N.update({f"kpi_{k}": v for k, v in ov.items()})

    item = kpis.build_item_kpis(panel)
    isk = kpis.build_item_state_kpis(panel, item)
    item.to_csv(cfg.TABLES / "kpi_item_kpis.csv", index=False)
    isk.round(4).to_csv(cfg.TABLES / "kpi_item_state_kpis.csv", index=False)

    # ------------------------------------------------------------------ 1. ABC / Pareto
    abc = item.groupby("abc_class").agg(n_items=("item_id", "size"), revenue=("revenue", "sum"), units=("units", "sum"),
                                        zero_week_share=("zero_week_share", "mean")).reset_index()
    abc["items_share"] = abc["n_items"] / abc["n_items"].sum()
    abc["revenue_share"] = abc["revenue"] / abc["revenue"].sum()
    abc["avg_selling_price"] = abc["revenue"] / abc["units"]
    abc.to_csv(cfg.TABLES / "kpi_abc_summary.csv", index=False)
    A = abc.set_index("abc_class")
    for c in "ABC":
        N[f"kpi_abc_{c}_n"], N[f"kpi_abc_{c}_items_share"], N[f"kpi_abc_{c}_revenue_share"] = int(A.loc[c, "n_items"]), A.loc[c, "items_share"], A.loc[c, "revenue_share"]
        N[f"kpi_abc_{c}_zero_week_share"] = A.loc[c, "zero_week_share"]
    n_items = len(item)
    N["kpi_top10pct_items_revenue_share"] = float(item["revenue"].head(int(round(0.10 * n_items))).sum() / item["revenue"].sum())
    N["kpi_top100_items_revenue_share"] = float(item["revenue"].head(100).sum() / item["revenue"].sum())
    N["kpi_top20pct_items_revenue_share"] = float(item["revenue"].head(int(round(0.20 * n_items))).sum() / item["revenue"].sum())
    N["kpi_top_item"], N["kpi_top_item_revenue"] = item.iloc[0]["item_id"], float(item.iloc[0]["revenue"])
    abc_cat = item.groupby(["cat_id", "abc_class"]).agg(n_items=("item_id", "size"), revenue=("revenue", "sum")).reset_index()
    abc_cat["share_of_category_items"] = abc_cat["n_items"] / abc_cat.groupby("cat_id")["n_items"].transform("sum")
    abc_cat["share_of_category_revenue"] = abc_cat["revenue"] / abc_cat.groupby("cat_id")["revenue"].transform("sum")
    abc_cat.to_csv(cfg.TABLES / "kpi_abc_by_category.csv", index=False)
    a_share = abc_cat[abc_cat["abc_class"] == "A"].set_index("cat_id")["share_of_category_items"]
    N["kpi_abc_A_items_share_max_cat"], N["kpi_abc_A_items_share_max"] = a_share.idxmax(), float(a_share.max())
    N["kpi_abc_A_items_share_min_cat"], N["kpi_abc_A_items_share_min"] = a_share.idxmin(), float(a_share.min())

    fig, axes = plt.subplots(1, 2, figsize=(14, 4.9), gridspec_kw={"width_ratios": [1.3, 1]})
    ax = axes[0]
    x = np.arange(1, n_items + 1) / n_items
    ax.plot(x, item["cum_revenue_share"], color=viz.PALETTE["main"], lw=2.5)
    ax.axhline(cfg.ABC_A_CUTOFF, color=viz.PALETTE["grey"], ls="--", lw=1); ax.axhline(cfg.ABC_B_CUTOFF, color=viz.PALETTE["grey"], ls="--", lw=1)
    ax.axvline(A.loc["A", "items_share"], color=viz.PALETTE["accent"], ls=":", lw=1.5)
    ax.axvline(A.loc["A", "items_share"] + A.loc["B", "items_share"], color=viz.PALETTE["accent"], ls=":", lw=1.5)
    ax.text(A.loc["A", "items_share"] / 2, 0.12, f"A\n{int(A.loc['A', 'n_items']):,} items\n{A.loc['A', 'items_share']:.0%} of items\n= {cfg.ABC_A_CUTOFF:.0%} of revenue", ha="center", fontsize=9)
    ax.text(A.loc["A", "items_share"] + A.loc["B", "items_share"] / 2, 0.12, f"B\n{int(A.loc['B', 'n_items']):,}", ha="center", fontsize=9)
    ax.text(0.86, 0.12, f"C\n{int(A.loc['C', 'n_items']):,}", ha="center", fontsize=9)
    viz.pct_axis(ax, "x"); viz.pct_axis(ax, "y")
    ax.set_xlabel("Share of items (sorted by revenue)"); ax.set_ylabel("Cumulative share of revenue"); ax.set_title("Pareto curve of item revenue (ABC classes)")
    p = abc_cat.pivot(index="cat_id", columns="abc_class", values="share_of_category_items")
    p.plot.barh(stacked=True, ax=axes[1], color=[viz.PALETTE["main"], viz.PALETTE["accent"], viz.PALETTE["grey"]])
    viz.pct_axis(axes[1], "x"); axes[1].set_ylabel(""); axes[1].set_title("ABC mix of items inside each category")
    axes[1].legend(title="ABC class", loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False)
    viz.save(fig, "kpi_01_pareto_abc")

    # ------------------------------------------------------------------ 2. ABC x variability (XYZ) matrix
    xyz = isk.dropna(subset=["cv_band"]).copy()
    cnt = xyz.pivot_table(index="abc_class", columns="cv_band", values="item_id", aggfunc="size", fill_value=0)[["stable", "variable", "erratic"]]
    rev = xyz.pivot_table(index="abc_class", columns="cv_band", values="revenue", aggfunc="sum", fill_value=0)[["stable", "variable", "erratic"]]
    rev_share = rev / rev.values.sum()
    out = pd.concat({"n_item_states": cnt, "revenue_share": rev_share}, axis=1)
    out.to_csv(cfg.TABLES / "kpi_abc_xyz_matrix.csv")
    N["kpi_A_stable_revenue_share"] = float(rev_share.loc["A", "stable"])
    N["kpi_A_erratic_revenue_share"] = float(rev_share.loc["A", "erratic"])
    N["kpi_A_variable_revenue_share"] = float(rev_share.loc["A", "variable"])
    N["kpi_C_erratic_n_share"] = float(cnt.loc["C", "erratic"] / cnt.loc["C"].sum())
    N["kpi_A_erratic_n_share"] = float(cnt.loc["A", "erratic"] / cnt.loc["A"].sum())
    N["kpi_cv_median_A"], N["kpi_cv_median_C"] = float(xyz.loc[xyz["abc_class"] == "A", "cv"].median()), float(xyz.loc[xyz["abc_class"] == "C", "cv"].median())

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))
    sns.heatmap(cnt, annot=True, fmt=",d", cmap="Blues", cbar=False, ax=axes[0]); axes[0].set_title("Item-states: ABC class x weekly demand variability"); axes[0].set_xlabel("Variability band (CV)"); axes[0].set_ylabel("ABC class")
    sns.heatmap(rev_share, annot=True, fmt=".1%", cmap="Oranges", cbar=False, ax=axes[1]); axes[1].set_title("Share of total revenue"); axes[1].set_xlabel("Variability band (CV)"); axes[1].set_ylabel("")
    viz.save(fig, "kpi_02_abc_variability_matrix")

    # ------------------------------------------------------------------ 3. demand classes and slow movers
    dc = isk.dropna(subset=["demand_class"]).groupby("demand_class").agg(n_item_states=("item_id", "size"), revenue=("revenue", "sum"),
                                                                         mean_zero_week_share=("zero_week_share", "mean")).reset_index()
    dc["share_of_item_states"] = dc["n_item_states"] / dc["n_item_states"].sum()
    dc["share_of_revenue"] = dc["revenue"] / dc["revenue"].sum()
    dc.to_csv(cfg.TABLES / "kpi_demand_class_summary.csv", index=False)
    D = dc.set_index("demand_class")
    for k in D.index:
        N[f"kpi_class_{k}_item_share"], N[f"kpi_class_{k}_revenue_share"] = D.loc[k, "share_of_item_states"], D.loc[k, "share_of_revenue"]
    non_smooth = D.drop(index="smooth")
    N["kpi_nonsmooth_item_share"], N["kpi_nonsmooth_revenue_share"] = float(non_smooth["share_of_item_states"].sum()), float(non_smooth["share_of_revenue"].sum())
    slow = item[(item["abc_class"] == "C") & (item["zero_week_share"] > cfg.SLOW_ZERO_SHARE)]
    slow.to_csv(cfg.TABLES / "kpi_slow_movers_C_items.csv", index=False)
    N["kpi_slow_C_n"], N["kpi_slow_C_revenue_share"] = len(slow), float(slow["revenue"].sum() / item["revenue"].sum())
    N["kpi_slow_C_share_of_C_items"] = float(len(slow) / A.loc["C", "n_items"])

    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    order = [k for k in ("smooth", "erratic", "intermittent", "lumpy") if k in D.index]
    xx = np.arange(len(order)); w = 0.38
    ax.bar(xx - w / 2, [D.loc[k, "share_of_item_states"] for k in order], w, color=viz.PALETTE["grey"], label="Share of item-states")
    ax.bar(xx + w / 2, [D.loc[k, "share_of_revenue"] for k in order], w, color=viz.PALETTE["main"], label="Share of revenue")
    ax.set_xticks(xx); ax.set_xticklabels(order); viz.pct_axis(ax); ax.legend(); ax.set_title("Demand classes: how many item-states vs how much revenue")
    viz.save(fig, "kpi_03_demand_classes")

    # ------------------------------------------------------------------ 4. price-cut uplift (association, not causation)
    g, units, price, _ = kpis.aggregate_item_state(panel)
    pcu = analysis.price_cut_uplift(units, price)
    pcu.to_csv(cfg.TABLES / "kpi_price_cut_uplift.csv", index=False)
    P = pcu.set_index("week_type")
    N["kpi_pcu_cut_share"] = float(P.loc["price-cut week", "share_of_weeks"])
    N["kpi_pcu_cut_n"] = int(P.loc["price-cut week", "n_item_state_weeks"])
    N["kpi_pcu_cut_median_ratio"], N["kpi_pcu_normal_median_ratio"] = float(P.loc["price-cut week", "median_unit_ratio"]), float(P.loc["normal week", "median_unit_ratio"])
    N["kpi_pcu_cut_mean_ratio"], N["kpi_pcu_normal_mean_ratio"] = float(P.loc["price-cut week", "mean_unit_ratio"]), float(P.loc["normal week", "mean_unit_ratio"])
    N["kpi_pcu_post_median_ratio"] = float(P.loc["week after a price cut", "median_unit_ratio"])
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(pcu["week_type"], pcu["median_unit_ratio"], color=[viz.PALETTE["accent"], viz.PALETTE["grey"], viz.PALETTE["main"]])
    for i, r in pcu.iterrows():
        ax.text(i, r["median_unit_ratio"], f"{r['median_unit_ratio']:.2f}x\n(n={r['n_item_state_weeks']:,})", ha="center", va="bottom", fontsize=9,
                bbox=dict(facecolor="white", edgecolor="none", pad=1.5))
    ax.axhline(1, color="black", ls=":", lw=1); ax.set_ylim(0, pcu["median_unit_ratio"].max() * 1.25)
    ax.set_ylabel("Median units vs previous 8-week average"); ax.set_title("Units in price-cut weeks (price <= 90% of recent average)")
    viz.save(fig, "kpi_04_price_cut_uplift")

    # ------------------------------------------------------------------ 5. ASSUMED safety stock / reorder point
    pol = isk.dropna(subset=["safety_stock_units"]).copy()
    z_class = pol["abc_class"].map(cfg.SERVICE_Z_BY_CLASS)
    pol["safety_stock_by_class_units"] = kpis.safety_stock(pol["std_units_last52"], z=z_class)
    pol["safety_stock_by_class_value"] = pol["safety_stock_by_class_units"] * pol["price_latest"]
    tot_ss = pol["safety_stock_retail_value"].sum()
    byc = pol.groupby("abc_class").agg(n_item_states=("item_id", "size"), safety_stock_units=("safety_stock_units", "sum"),
                                       safety_stock_retail_value=("safety_stock_retail_value", "sum"),
                                       safety_stock_by_class_value=("safety_stock_by_class_value", "sum"),
                                       median_weeks_of_cover=("safety_stock_weeks_of_cover", "median"),
                                       revenue=("revenue", "sum")).reset_index()
    byc["share_of_ss_value"] = byc["safety_stock_retail_value"] / tot_ss
    byc["share_of_revenue"] = byc["revenue"] / byc["revenue"].sum()
    byc.to_csv(cfg.TABLES / "kpi_policy_assumed_by_abc.csv", index=False)
    bycv = pol.groupby("cv_band").agg(n_item_states=("item_id", "size"), safety_stock_retail_value=("safety_stock_retail_value", "sum"),
                                      median_weeks_of_cover=("safety_stock_weeks_of_cover", "median")).reindex(["stable", "variable", "erratic"]).reset_index()
    bycv["share_of_ss_value"] = bycv["safety_stock_retail_value"] / tot_ss
    bycv.to_csv(cfg.TABLES / "kpi_policy_assumed_by_cv_band.csv", index=False)
    pol[["item_id", "state_id", "cat_id", "abc_class", "cv_band", "mean_units_last52", "std_units_last52", "price_latest", "safety_stock_units",
         "reorder_point_units", "order_up_to_units", "safety_stock_retail_value", "safety_stock_weeks_of_cover"]].round(3).to_csv(
        cfg.TABLES / "kpi_policy_assumed_item_state.csv", index=False)
    B = byc.set_index("abc_class")
    N.update(pol_lead_time_weeks=cfg.ASSUMED_LEAD_TIME_WEEKS, pol_review_weeks=cfg.REVIEW_PERIOD_WEEKS, pol_service_z=cfg.SERVICE_Z,
             pol_n_item_states=len(pol), pol_ss_retail_value=float(tot_ss), pol_ss_units=float(pol["safety_stock_units"].sum()),
             pol_ss_median_weeks_cover=float(pol["safety_stock_weeks_of_cover"].median()),
             pol_ss_value_A_share=float(B.loc["A", "share_of_ss_value"]), pol_ss_value_C_share=float(B.loc["C", "share_of_ss_value"]),
             pol_ss_value_by_class=float(pol["safety_stock_by_class_value"].sum()),
             pol_ss_change_by_class=float(pol["safety_stock_by_class_value"].sum() / tot_ss - 1),
             pol_z_A=cfg.SERVICE_Z_BY_CLASS["A"], pol_z_B=cfg.SERVICE_Z_BY_CLASS["B"], pol_z_C=cfg.SERVICE_Z_BY_CLASS["C"],
             pol_erratic_ss_share=float(bycv.set_index("cv_band").loc["erratic", "share_of_ss_value"]),
             pol_erratic_item_share=float(bycv.set_index("cv_band").loc["erratic", "n_item_states"] / len(pol)),
             pol_ss_value_per_100_revenue=float(100 * tot_ss / (pol["revenue"].sum() / panel.n_weeks * 52)))

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    axes[0].bar(byc["abc_class"], byc["share_of_ss_value"], width=0.38, align="edge", color=viz.PALETTE["accent"], label="Share of safety-stock value")
    axes[0].bar(byc["abc_class"], byc["share_of_revenue"], width=-0.38, align="edge", color=viz.PALETTE["main"], label="Share of revenue")
    viz.pct_axis(axes[0]); axes[0].legend(); axes[0].set_title("ASSUMED (1-week lead time): safety stock vs revenue")
    axes[1].bar(bycv["cv_band"], bycv["median_weeks_of_cover"], color=viz.PALETTE["grey"])
    axes[1].set_ylabel("Safety stock, weeks of average demand"); axes[1].set_title("ASSUMED: median safety-stock cover")
    viz.save(fig, "kpi_05_assumed_safety_stock")

    # ------------------------------------------------------------------ 6. store view
    store = kpis.build_cut_kpis(panel, "store_id")
    store.to_csv(cfg.TABLES / "kpi_store_kpis.csv", index=False)
    N["kpi_store_zero_week_max"] = store["zero_week_share"].max()

    nums.save(N)
    for k, v in N.items():
        print(f"{k:<44} {v}")


if __name__ == "__main__":
    main()
