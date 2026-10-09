"""
Step 6 - KPI analysis: fill rate, stockouts, turnover, days of inventory, ABC, demand variability (CV),
lead times, reorder point / safety stock check.

Reads  data/processed/*.csv
Writes outputs/tables/kpi_*.csv, outputs/charts/kpi_*.png, adds numbers to outputs/tables/key_numbers.json

Run:  python src/06_kpi_analysis.py
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import config as cfg
import keynums as nums
import kpis
import viz


def main():
    cfg.ensure_dirs()
    viz.setup()
    t = kpis.load_clean()
    N = {}

    overall = kpis.build_overall_kpis(t)
    sku = kpis.build_sku_kpis(t)
    n_days = int(overall["n_days"])
    cat = kpis.build_cut_kpis(t, "category").sort_values("fill_rate")
    whs = kpis.build_cut_kpis(t, "warehouse_code").merge(t["warehouses"][["warehouse_code", "region"]], on="warehouse_code").sort_values("fill_rate")
    reg = kpis.build_cut_kpis(t, "wh_region").sort_values("fill_rate")
    monthly = kpis.build_monthly_kpis(t)
    abc = kpis.build_abc_summary(sku, n_days)
    lt_sup = kpis.build_lead_time_by(t, "supplier_code")
    lt_mode = kpis.build_lead_time_by(t, "ship_mode")
    lt_reg = kpis.build_lead_time_by(t, "supplier_region")
    policy = kpis.build_policy_check(t)

    # ---------------------------------------------------------------- save tables
    pd.DataFrame([overall]).to_csv(cfg.TABLES / "kpi_overall.csv", index=False)
    for name, df in dict(sku=sku, category=cat, warehouse=whs, region=reg, monthly=monthly, abc_summary=abc,
                         lead_time_supplier=lt_sup, lead_time_mode=lt_mode, lead_time_region=lt_reg,
                         policy_check=policy).items():
        df.to_csv(cfg.TABLES / f"kpi_{name}.csv", index=False)

    # ---------------------------------------------------------------- context numbers used in the docs
    d0, d1 = t["demand_daily"]["date"].min(), t["demand_daily"]["date"].max()
    N.update(kpi_start_date=str(d0.date()), kpi_end_date=str(d1.date()), n_categories=t["products"]["category"].nunique(),
             n_warehouses=len(t["warehouses"]), n_suppliers=len(t["suppliers"]),
             pol_set_date=str(t["inventory_policy"]["policy_set_date"].max().date()),
             pol_set_week=int((t["inventory_policy"]["policy_set_date"].max() - d0).days // 7 + 1))

    # ---------------------------------------------------------------- headline
    N.update(kpi_fill_rate=overall["fill_rate"], kpi_stockout_rate=overall["stockout_rate"],
             kpi_revenue=overall["revenue"], kpi_lost_revenue=overall["lost_revenue"],
             kpi_lost_revenue_pct=overall["lost_revenue"] / (overall["revenue"] + overall["lost_revenue"]),
             kpi_turnover=overall["inventory_turnover"], kpi_doi=overall["days_of_inventory"],
             kpi_avg_inventory_value=overall["avg_inventory_value"], kpi_n_skus=overall["n_skus"],
             kpi_n_days=n_days, kpi_units_demanded=overall["units_demanded"])

    # ---------------------------------------------------------------- 1. monthly fill rate & stockout rate
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(monthly["month"], monthly["fill_rate"], marker="o", color=viz.PALETTE["main"], label="Fill rate")
    ax.plot(monthly["month"], 1 - monthly["stockout_rate"], marker="s", color=viz.PALETTE["accent"], label="1 - stockout rate (days fully served)")
    ax.axhline(cfg.FILL_RATE_TARGET, color=viz.PALETTE["good"], ls="--", lw=1.2, label=f"{cfg.FILL_RATE_TARGET:.0%} service target")
    viz.pct_axis(ax); ax.set_ylim(0.6, 1.0)
    ax.set_title("Service level by month"); ax.legend(loc="lower left")
    viz.save(fig, "kpi_01_monthly_fill_stockout")
    first3, last3 = monthly.head(3), monthly.tail(3)
    N["kpi_fill_first_3m"] = first3["fill_rate"].mean()
    N["kpi_fill_last_3m"] = last3["fill_rate"].mean()
    N["kpi_fill_worst_month"] = str(monthly.loc[monthly["fill_rate"].idxmin(), "month"].date())[:7]
    N["kpi_fill_worst_month_value"] = monthly["fill_rate"].min()
    N["kpi_months_above_target"] = int((monthly["fill_rate"] >= cfg.FILL_RATE_TARGET).sum())
    N["kpi_n_months"] = len(monthly)
    N["kpi_target"] = cfg.FILL_RATE_TARGET

    # ---------------------------------------------------------------- 2. fill rate by category and warehouse
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    axes[0].barh(cat["category"], cat["fill_rate"], color=viz.PALETTE["main"])
    axes[0].axvline(cfg.FILL_RATE_TARGET, color=viz.PALETTE["good"], ls="--"); viz.pct_axis(axes[0], "x"); axes[0].set_xlim(0.6, 1.0)
    axes[0].set_title("Fill rate by category")
    for i, v in enumerate(cat["fill_rate"]):
        axes[0].text(v + 0.003, i, f"{v:.1%}", va="center", fontsize=9)
    axes[1].barh(whs["warehouse_code"], whs["fill_rate"], color=viz.PALETTE["accent"])
    axes[1].axvline(cfg.FILL_RATE_TARGET, color=viz.PALETTE["good"], ls="--"); viz.pct_axis(axes[1], "x"); axes[1].set_xlim(0.6, 1.0)
    axes[1].set_title("Fill rate by warehouse")
    for i, v in enumerate(whs["fill_rate"]):
        axes[1].text(v + 0.003, i, f"{v:.1%}", va="center", fontsize=9)
    viz.save(fig, "kpi_02_fill_rate_category_warehouse")
    N.update(kpi_worst_category=cat.iloc[0]["category"], kpi_worst_category_fill=cat.iloc[0]["fill_rate"],
             kpi_best_category=cat.iloc[-1]["category"], kpi_best_category_fill=cat.iloc[-1]["fill_rate"],
             kpi_worst_category_lost_revenue=cat.iloc[0]["lost_revenue"],
             kpi_worst_warehouse=whs.iloc[0]["warehouse_code"], kpi_worst_warehouse_fill=whs.iloc[0]["fill_rate"],
             kpi_best_warehouse=whs.iloc[-1]["warehouse_code"], kpi_best_warehouse_fill=whs.iloc[-1]["fill_rate"])
    top_lost_cat = cat.sort_values("lost_revenue", ascending=False).iloc[0]
    N["kpi_top_lost_category"] = top_lost_cat["category"]
    N["kpi_top_lost_category_share"] = top_lost_cat["lost_revenue"] / cat["lost_revenue"].sum()

    # ---------------------------------------------------------------- 3. turnover & days of inventory by category
    inv_cat = cat.sort_values("inventory_turnover")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))
    axes[0].barh(inv_cat["category"], inv_cat["inventory_turnover"], color=viz.PALETTE["main"])
    axes[0].set_title("Inventory turnover (times per year)")
    for i, v in enumerate(inv_cat["inventory_turnover"]):
        axes[0].text(v + 0.3, i, f"{v:.1f}", va="center", fontsize=9)
    cat_doi = sku.groupby("category").apply(lambda g: g["avg_inventory_units"].sum() / (g["units_fulfilled"].sum() / n_days), include_groups=False)
    cat_doi = cat_doi.loc[inv_cat["category"]]
    axes[1].barh(cat_doi.index, cat_doi.values, color=viz.PALETTE["accent"])
    axes[1].set_title("Days of inventory (units basis)")
    for i, v in enumerate(cat_doi.values):
        axes[1].text(v + 0.2, i, f"{v:.1f}", va="center", fontsize=9)
    viz.save(fig, "kpi_03_turnover_doi_category")
    N["kpi_turnover_best_category"] = inv_cat.iloc[-1]["category"]
    N["kpi_turnover_best_value"] = inv_cat.iloc[-1]["inventory_turnover"]
    N["kpi_turnover_worst_category"] = inv_cat.iloc[0]["category"]
    N["kpi_turnover_worst_value"] = inv_cat.iloc[0]["inventory_turnover"]
    N["kpi_turnover_worst_inv_share"] = inv_cat.iloc[0]["avg_inventory_value"] / cat["avg_inventory_value"].sum()

    # ---------------------------------------------------------------- 4. ABC pareto
    s = sku.sort_values("revenue", ascending=False).reset_index(drop=True)
    cum = s["revenue"].cumsum() / s["revenue"].sum()
    fig, ax = plt.subplots(figsize=(11, 4.8))
    colors = s["abc_class"].map({"A": viz.PALETTE["main"], "B": viz.PALETTE["accent"], "C": viz.PALETTE["grey"]})
    ax.bar(range(len(s)), s["revenue"] / 1e6, color=colors)
    ax.set_ylabel("Revenue ($M)"); ax.set_xlabel("SKUs ranked by revenue")
    ax2 = ax.twinx()
    ax2.plot(range(len(s)), cum, color="black", lw=2); ax2.set_ylim(0, 1.02); viz.pct_axis(ax2)
    ax2.axhline(cfg.ABC_A_CUTOFF, ls="--", color=viz.PALETTE["bad"], lw=1); ax2.axhline(cfg.ABC_B_CUTOFF, ls="--", color=viz.PALETTE["bad"], lw=1)
    ax2.set_ylabel("Cumulative share of revenue"); ax2.grid(False)
    ax.set_title("ABC / Pareto analysis (blue = A, orange = B, grey = C)")
    viz.save(fig, "kpi_04_abc_pareto")
    a, b, c = (abc.set_index("abc_class").loc[k] for k in "ABC")
    N.update(abc_a_skus=a["n_skus"], abc_b_skus=b["n_skus"], abc_c_skus=c["n_skus"],
             abc_a_sku_share=a["n_skus"] / len(sku), abc_a_revenue_share=a["revenue_share"],
             abc_c_revenue_share=c["revenue_share"], abc_c_sku_share=c["n_skus"] / len(sku),
             abc_a_inventory_share=a["inventory_share"], abc_c_inventory_share=c["inventory_share"],
             abc_a_fill=a["fill_rate"], abc_b_fill=b["fill_rate"], abc_c_fill=c["fill_rate"],
             abc_a_turnover=a["inventory_turnover"], abc_c_turnover=c["inventory_turnover"],
             abc_a_lost_revenue=a["lost_revenue"], abc_a_lost_revenue_share=a["lost_revenue"] / abc["lost_revenue"].sum())

    # ---------------------------------------------------------------- 5. ABC x CV matrix + ABC service
    matrix = pd.crosstab(sku["abc_class"], sku["cv_band"]).reindex(columns=["Low", "Medium", "High"], fill_value=0)
    matrix.to_csv(cfg.TABLES / "kpi_abc_cv_matrix.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8))
    sns.heatmap(matrix, annot=True, fmt="d", cmap="Blues", cbar=False, ax=axes[0])
    axes[0].set_title("Number of SKUs: ABC class x demand variability"); axes[0].set_ylabel("ABC class"); axes[0].set_xlabel("Demand CV band")
    axes[1].bar(abc["abc_class"], abc["fill_rate"], color=[viz.PALETTE["main"], viz.PALETTE["accent"], viz.PALETTE["grey"]])
    axes[1].axhline(cfg.FILL_RATE_TARGET, color=viz.PALETTE["good"], ls="--"); viz.pct_axis(axes[1]); axes[1].set_ylim(0.6, 1.0)
    axes[1].set_title("Fill rate by ABC class")
    for i, v in enumerate(abc["fill_rate"]):
        axes[1].text(i, v + 0.005, f"{v:.1%}", ha="center")
    viz.save(fig, "kpi_05_abc_cv_matrix_and_service")
    N["abc_a_high_cv_count"] = int(matrix.loc["A", "High"]) if "A" in matrix.index else 0
    N["abc_a_medium_high_cv_count"] = int(matrix.loc["A", ["Medium", "High"]].sum())

    # ---------------------------------------------------------------- 6. top lost-revenue SKUs
    top = sku.sort_values("lost_revenue", ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(top["sku"], top["lost_revenue"] / 1e6, color=top["abc_class"].map({"A": viz.PALETTE["main"], "B": viz.PALETTE["accent"], "C": viz.PALETTE["grey"]}))
    ax.invert_yaxis(); ax.set_xlabel("Lost revenue ($M, 2 years)"); ax.set_title("Top 15 SKUs by lost revenue (stockouts)")
    viz.save(fig, "kpi_06_top_lost_revenue_skus")
    N["kpi_top15_lost_share"] = top["lost_revenue"].sum() / sku["lost_revenue"].sum()
    N["kpi_top15_a_count"] = int((top["abc_class"] == "A").sum())
    N["kpi_top_lost_sku"] = top.iloc[0]["sku"]
    N["kpi_top_lost_sku_value"] = top.iloc[0]["lost_revenue"]

    # ---------------------------------------------------------------- 7. days of inventory vs service
    N["kpi_doi_median_sku"] = sku["days_of_inventory"].median()
    N["kpi_doi_min_sku"] = sku["days_of_inventory"].min()
    N["kpi_doi_max_sku"] = sku["days_of_inventory"].max()
    N["kpi_corr_doi_fill"] = float(sku["days_of_inventory"].corr(sku["fill_rate"]))
    q = pd.qcut(sku["days_of_inventory"].rank(method="first"), 4, labels=False)
    lowq, highq = sku[q == 0], sku[q == 3]
    N["kpi_fill_lowest_doi_quartile"] = lowq["units_fulfilled"].sum() / lowq["units_demanded"].sum()
    N["kpi_fill_highest_doi_quartile"] = highq["units_fulfilled"].sum() / highq["units_demanded"].sum()
    N["kpi_doi_lowest_quartile_max"] = lowq["days_of_inventory"].max()
    fig, ax = plt.subplots(figsize=(8, 4.8))
    sc = ax.scatter(sku["days_of_inventory"], sku["fill_rate"], c=sku["demand_cv"], cmap="viridis", s=60, alpha=0.85)
    plt.colorbar(sc, label="Demand CV"); viz.pct_axis(ax)
    ax.set_xlabel("Days of inventory"); ax.set_ylabel("Fill rate"); ax.set_title("Days of inventory vs fill rate (one dot = one SKU)")
    viz.save(fig, "kpi_07_doi_vs_fill_rate")

    # ---------------------------------------------------------------- 8. lead times
    dm = lt_mode.sort_values("avg_actual_days")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    x = np.arange(len(dm)); w = 0.38
    axes[0].bar(x - w / 2, dm["avg_promised_days"], w, label="Promised", color=viz.PALETTE["grey"])
    axes[0].bar(x + w / 2, dm["avg_actual_days"], w, label="Actual", color=viz.PALETTE["main"])
    axes[0].set_xticks(x); axes[0].set_xticklabels(dm["ship_mode"]); axes[0].set_ylabel("Days"); axes[0].legend()
    axes[0].set_title("Lead time by shipping mode: promised vs actual")
    sc = lt_sup.sort_values("on_time_rate")
    colmap = dict(zip(sorted(sc["supplier_region"].unique()), sns.color_palette("Set2", 5)))
    axes[1].barh(sc["supplier_code"], sc["on_time_rate"], color=[colmap[r] for r in sc["supplier_region"]])
    viz.pct_axis(axes[1], "x"); axes[1].set_title("Supplier on-time delivery rate")
    axes[1].tick_params(axis="y", labelsize=7)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colmap.values()]
    axes[1].legend(handles, colmap.keys(), fontsize=8, loc="lower right")
    viz.save(fig, "kpi_08_lead_time_mode_supplier")
    po = kpis.delivered_pos(t["purchase_orders"])
    N["lt_n_delivered_pos"] = len(po)
    N["lt_avg_promised"] = po["promised_lead_days"].mean()
    N["lt_avg_actual"] = po["actual_lead_days"].mean()
    N["lt_on_time_rate"] = po["on_time_flag"].mean()
    N["lt_avg_delay_when_late"] = po.loc[po["delay_days"] > 0, "delay_days"].mean()
    N["lt_worst_supplier"] = lt_sup.iloc[0]["supplier_code"]
    N["lt_worst_supplier_on_time"] = lt_sup.iloc[0]["on_time_rate"]
    N["lt_best_supplier"] = lt_sup.iloc[-1]["supplier_code"]
    N["lt_best_supplier_on_time"] = lt_sup.iloc[-1]["on_time_rate"]
    N["lt_supplier_on_time_spread"] = lt_sup["on_time_rate"].max() - lt_sup["on_time_rate"].min()
    N["lt_lead_time_cv_overall"] = po["actual_lead_days"].std() / po["actual_lead_days"].mean()
    air = lt_mode.set_index("ship_mode").loc["air"]
    nonair = po[po["ship_mode"] != "air"]
    N["lt_air_po_share"] = len(po[po["ship_mode"] == "air"]) / len(po)
    N["lt_air_freight_pct"] = air["freight_pct_of_value"]
    N["lt_nonair_freight_pct"] = nonair["freight_cost"].sum() / nonair["po_value"].sum()
    N["lt_air_extra_freight"] = air["freight_cost"] - air["po_value"] * N["lt_nonair_freight_pct"]
    N["lt_slowest_region"] = lt_reg.sort_values("avg_actual_days").iloc[-1]["supplier_region"]
    N["lt_slowest_region_days"] = lt_reg["avg_actual_days"].max()
    N["lt_fastest_region"] = lt_reg.sort_values("avg_actual_days").iloc[0]["supplier_region"]
    N["lt_fastest_region_days"] = lt_reg["avg_actual_days"].min()
    N["lt_ocean_po_share"] = len(po[po["ship_mode"] == "ocean"]) / len(po)
    N["lt_invalid_date_pos"] = int(t["purchase_orders"]["delivery_date_invalid"].sum())

    # ---------------------------------------------------------------- 9. policy vs recommended (reorder point / safety stock)
    under = policy[policy["under_protected"] == 1]
    ok = policy[policy["under_protected"] == 0]
    N["pol_n_sku_wh"] = len(policy)
    N["pol_under_n"] = len(under)
    N["pol_under_share"] = len(under) / len(policy)
    N["pol_stockout_under"] = under["recent_stockout_rate"].mean()
    N["pol_stockout_ok"] = ok["recent_stockout_rate"].mean() if len(ok) else np.nan
    N["pol_ok_n"] = len(ok)
    N["pol_median_gap_pct_under"] = under["rop_gap_pct"].median()
    N["pol_extra_inventory_value"] = policy["extra_inventory_value_needed"].sum()
    N["pol_median_ss_ratio"] = float((policy["rec_safety_stock"] / policy["safety_stock_units"]).median())
    N["pol_extra_inventory_pct_of_avg"] = N["pol_extra_inventory_value"] / overall["avg_inventory_value"]
    N["pol_recent_lost_revenue_under"] = under["recent_lost_revenue"].sum()
    N["pol_recent_lost_revenue_total"] = policy["recent_lost_revenue"].sum()
    policy["gap_band"] = pd.qcut(policy["rop_gap_pct"].rank(method="first"), 4, labels=["Q1 smallest gap", "Q2", "Q3", "Q4 largest gap"])
    band = policy.groupby("gap_band", observed=True)["recent_stockout_rate"].mean()
    N["pol_stockout_q1"] = band.iloc[0]
    N["pol_stockout_q4"] = band.iloc[-1]
    N["pol_corr_gap_stockout"] = float(policy["rop_gap_pct"].corr(policy["recent_stockout_rate"]))
    policy.to_csv(cfg.TABLES / "kpi_policy_check.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    axes[0].scatter(policy["reorder_point_units"], policy["rec_reorder_point"], s=18, alpha=0.7, color=viz.PALETTE["main"])
    lim = [max(1, policy[["reorder_point_units", "rec_reorder_point"]].min().min()), policy[["reorder_point_units", "rec_reorder_point"]].max().max()]
    axes[0].plot(lim, lim, color=viz.PALETTE["bad"], ls="--", label="current = recommended")
    axes[0].set_xscale("log"); axes[0].set_yscale("log"); axes[0].legend()
    axes[0].set_xlabel("Current reorder point (units)"); axes[0].set_ylabel("Recommended reorder point (units)")
    axes[0].set_title("Points above the line = under-protected")
    axes[1].bar(band.index.astype(str), band.values, color=[viz.PALETTE["good"], "#9bc53d", viz.PALETTE["accent"], viz.PALETTE["bad"]])
    viz.pct_axis(axes[1]); axes[1].set_ylabel("Stockout-day rate, last 13 weeks")
    axes[1].set_title("Bigger policy gap -> more stockouts"); axes[1].tick_params(axis="x", labelsize=8)
    viz.save(fig, "kpi_09_policy_gap_vs_stockouts")

    nums.save(N)
    for k, v in N.items():
        print(f"{k:<38} {v}")


if __name__ == "__main__":
    main()
