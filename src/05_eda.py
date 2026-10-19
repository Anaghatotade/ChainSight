"""
Step 5 - Exploratory data analysis (EDA) on the real M5 data.

Questions answered (each chart ends with a "so what" in the README):
  * how is demand trending - and how much of the growth is just MORE items on sale?
  * which categories / departments / stores matter?
  * how seasonal is demand, and what is the weekday pattern?
  * how many items sell only occasionally (intermittent demand)?
  * how often do prices change, and what do SNAP days and events do?

Reads  data/processed/*, outputs/sql_results/*.csv (calendar and price queries were done in SQL)
Writes outputs/charts/eda_*.png, outputs/tables/eda_*.csv, adds numbers to outputs/tables/key_numbers.json

Run:  python src/05_eda.py
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import analysis
import config as cfg
import keynums as nums
import kpis
import panel as pn
import viz

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def sql_result(name):
    return pd.read_csv(cfg.SQL_RESULTS / f"{name}.csv")


def main():
    cfg.ensure_dirs()
    viz.setup()
    panel = pn.load_panel()
    daily = pd.read_csv(cfg.DATA_PROCESSED / "daily_store_dept.csv", parse_dates=["date"])
    N = {}
    on = panel.onsale
    weeks = kpis.weekly_totals(panel)
    weeks.to_csv(cfg.TABLES / "eda_weekly_totals.csv", index=False)

    # ------------------------------------------------------------------ 1. trend and assortment growth
    yearly = weeks.groupby("year").agg(n_weeks=("week_idx", "size"), units=("units", "sum"), revenue=("revenue", "sum"),
                                       series_on_sale_avg=("n_series_on_sale", "mean")).reset_index()
    yearly["revenue_per_week"] = yearly["revenue"] / yearly["n_weeks"]
    yearly["revenue_per_on_sale_series_week"] = yearly["revenue"] / (yearly["series_on_sale_avg"] * yearly["n_weeks"])
    yearly["partial_year"] = yearly["n_weeks"] < 52
    yearly.to_csv(cfg.TABLES / "eda_yearly_summary.csv", index=False)
    full = yearly[~yearly["partial_year"]].set_index("year")
    y0, y1 = int(full.index.min()), int(full.index.max())
    n_years = y1 - y0
    N["eda_first_full_year"], N["eda_last_full_year"] = y0, y1
    N["eda_rev_per_week_cagr"] = (full.loc[y1, "revenue_per_week"] / full.loc[y0, "revenue_per_week"]) ** (1 / n_years) - 1
    N["eda_rev_per_week_growth_total"] = full.loc[y1, "revenue_per_week"] / full.loc[y0, "revenue_per_week"] - 1
    N["eda_rev_per_week_yoy_last"] = full.loc[y1, "revenue_per_week"] / full.loc[y1 - 1, "revenue_per_week"] - 1
    N["eda_lfl_growth_total"] = full.loc[y1, "revenue_per_on_sale_series_week"] / full.loc[y0, "revenue_per_on_sale_series_week"] - 1
    N["eda_series_on_sale_first_week"], N["eda_series_on_sale_last_week"] = int(weeks["n_series_on_sale"].iloc[0]), int(weeks["n_series_on_sale"].iloc[-1])
    N["eda_assortment_growth"] = weeks["n_series_on_sale"].iloc[-1] / weeks["n_series_on_sale"].iloc[0] - 1
    N["eda_units_per_week_avg"] = float(weeks["units"].mean())

    fig, axes = plt.subplots(1, 2, figsize=(14, 4.8))
    ax = axes[0]
    ax.plot(weeks["week_start"], weeks["units"], color=viz.PALETTE["grey"], lw=1, label="Weekly units")
    ax.plot(weeks["week_start"], weeks["units"].rolling(52).mean(), color=viz.PALETTE["main"], lw=2.5, label="52-week average")
    ax.set_title("Total weekly unit sales (all 10 stores)"); ax.set_ylabel("Units per week"); ax.legend()
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v / 1e3:,.0f}K"))
    ax = axes[1]
    cat_rev = pd.DataFrame(panel.revenue()).groupby(panel.series["cat_id"].to_numpy()).sum().T
    cat_rev.index = weeks["week_start"]
    for c in cat_rev.columns:
        ax.plot(cat_rev.index, cat_rev[c].rolling(4).mean(), color=viz.CAT_COLORS[c], lw=2, label=c.title())
    ax.set_title("Weekly revenue by category (4-week average)"); ax.legend(); viz.money_axis(ax, unit=1e3, suffix="K")
    viz.save(fig, "eda_01_weekly_trend")

    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6))
    axes[0].plot(weeks["week_start"], weeks["n_series_on_sale"], color=viz.PALETTE["accent"], lw=2)
    axes[0].set_ylim(0, 31000); axes[0].axhline(panel.n_series, color="black", ls=":", lw=1)
    axes[0].set_title("Item-store series on sale per week (dotted = all 30,490)")
    axes[0].set_ylabel("Series on sale")
    ax = axes[1]
    ax.bar(yearly["year"].astype(str), yearly["revenue_per_week"], color=[viz.PALETTE["grey"] if p else viz.PALETTE["main"] for p in yearly["partial_year"]])
    for i, r in yearly.iterrows():
        ax.text(i, r["revenue_per_week"], f"${r['revenue_per_week'] / 1e3:,.0f}K", ha="center", va="bottom", fontsize=9)
    ax.set_title("Revenue per week by year (grey = partial year)"); viz.money_axis(ax, unit=1e3, suffix="K")
    viz.save(fig, "eda_02_assortment_and_yearly_growth")

    # ------------------------------------------------------------------ 2. category / department / store mix
    cat = kpis.build_cut_kpis(panel, "cat_id"); dept = kpis.build_cut_kpis(panel, "dept_id")
    store = kpis.build_cut_kpis(panel, "store_id"); state = kpis.build_cut_kpis(panel, "state_id")
    store = store.merge(panel.series.drop_duplicates("store_id")[["store_id", "state_id"]], on="store_id")
    for name, df in (("category", cat), ("department", dept), ("store", store), ("state", state)):
        df.to_csv(cfg.TABLES / f"eda_{name}_summary.csv", index=False)
    for _, r in cat.iterrows():
        N[f"eda_cat_share_{r['cat_id']}"] = r["revenue_share"]
    N["eda_top_dept"], N["eda_top_dept_share"] = dept.iloc[0]["dept_id"], dept.iloc[0]["revenue_share"]
    N["eda_top_store"], N["eda_top_store_share"] = store.iloc[0]["store_id"], store.iloc[0]["revenue_share"]
    N["eda_bottom_store"], N["eda_bottom_store_share"] = store.iloc[-1]["store_id"], store.iloc[-1]["revenue_share"]
    N["eda_store_top_vs_bottom"] = store.iloc[0]["revenue"] / store.iloc[-1]["revenue"]
    N["eda_top_state"], N["eda_top_state_share"] = state.iloc[0]["state_id"], state.iloc[0]["revenue_share"]
    N["eda_foods_units_share"] = float(panel.units[(panel.series["cat_id"] == "FOODS").to_numpy()].sum() / panel.units.sum())

    mix = pd.DataFrame(panel.revenue()).groupby([panel.series["store_id"].to_numpy(), panel.series["cat_id"].to_numpy()]).sum().sum(axis=1).unstack()
    mix = mix.div(mix.sum(axis=1), axis=0)
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), gridspec_kw={"width_ratios": [1, 1.4, 1.2]})
    axes[0].bar(cat["cat_id"].str.title(), cat["revenue_share"], color=[viz.CAT_COLORS[c] for c in cat["cat_id"]])
    for i, r in cat.iterrows():
        axes[0].text(i, r["revenue_share"], f"{r['revenue_share']:.0%}", ha="center", va="bottom")
    viz.pct_axis(axes[0]); axes[0].set_title("Revenue share by category")
    d = dept.sort_values("revenue")
    axes[1].barh(d["dept_id"], d["revenue"], color=[viz.CAT_COLORS[x.split("_")[0]] for x in d["dept_id"]])
    axes[1].set_title("Revenue by department"); viz.money_axis(axes[1], axis="x", unit=1e6, suffix="M")
    s = store.sort_values("revenue")
    cols = {"CA": viz.PALETTE["main"], "TX": viz.PALETTE["accent"], "WI": viz.PALETTE["good"]}
    axes[2].barh(s["store_id"], s["revenue"], color=[cols[x] for x in s["state_id"]])
    axes[2].set_title("Revenue by store (blue CA, orange TX, green WI)"); viz.money_axis(axes[2], axis="x", unit=1e6, suffix="M")
    viz.save(fig, "eda_03_category_dept_store_mix")
    mix.round(4).to_csv(cfg.TABLES / "eda_store_category_mix.csv")

    # ------------------------------------------------------------------ 3. seasonality and weekday pattern
    seas = analysis.seasonality_index(panel, "dept_id")
    seas.columns = MONTHS
    seas.round(4).to_csv(cfg.TABLES / "eda_seasonality_index_dept_month.csv")
    swing = (seas.max(axis=1) - seas.min(axis=1)).sort_values(ascending=False)
    N["eda_seasonality_years"] = ", ".join(str(y) for y in analysis.complete_years(panel.weeks))
    N["eda_most_seasonal_dept"], N["eda_most_seasonal_swing"] = swing.index[0], float(swing.iloc[0])
    N["eda_least_seasonal_dept"], N["eda_least_seasonal_swing"] = swing.index[-1], float(swing.iloc[-1])
    N["eda_most_seasonal_peak_month"] = seas.loc[swing.index[0]].idxmax()
    N["eda_most_seasonal_trough_month"] = seas.loc[swing.index[0]].idxmin()
    N["eda_most_seasonal_peak_index"], N["eda_most_seasonal_trough_index"] = float(seas.loc[swing.index[0]].max()), float(seas.loc[swing.index[0]].min())
    cat_seas = analysis.seasonality_index(panel, "cat_id"); cat_seas.columns = MONTHS
    for c, row in cat_seas.iterrows():
        N[f"eda_peak_month_{c}"], N[f"eda_swing_{c}"] = row.idxmax(), float(row.max() - row.min())
    wd = analysis.weekday_index(daily)
    wd.round(4).to_csv(cfg.TABLES / "eda_weekday_index_category.csv")
    wd_all = wd.mean(axis=0)
    N["eda_weekday_peak"], N["eda_weekday_peak_index"] = wd_all.idxmax(), float(wd_all.max())
    N["eda_weekday_trough"], N["eda_weekday_trough_index"] = wd_all.idxmin(), float(wd_all.min())
    N["eda_weekday_peak_vs_trough"] = float(wd_all.max() / wd_all.min())

    fig, axes = plt.subplots(1, 2, figsize=(15, 4.8), gridspec_kw={"width_ratios": [1.5, 1]})
    import seaborn as sns
    sns.heatmap(seas, annot=True, fmt=".2f", cmap="RdYlBu_r", center=1.0, cbar_kws={"label": "Index (1.00 = average month)"}, ax=axes[0])
    axes[0].set_title(f"Seasonality by department and month (complete years {N['eda_seasonality_years']})"); axes[0].set_ylabel("")
    for c in wd.index:
        axes[1].plot([x[:3] for x in wd.columns], wd.loc[c].values, marker="o", color=viz.CAT_COLORS[c], label=c.title(), lw=2)
    axes[1].axhline(1, color="black", ls=":", lw=1); axes[1].set_title("Weekday pattern (1.00 = average day)"); axes[1].legend()
    viz.save(fig, "eda_04_seasonality_and_weekday")

    # ------------------------------------------------------------------ 4. SNAP days, events and price changes (SQL results)
    snap = sql_result("05_price_and_events__snap_day_effect")
    ev_t = sql_result("05_price_and_events__event_uplift_by_type")
    ev_e = sql_result("05_price_and_events__event_uplift_by_event")
    pc = sql_result("05_price_and_events__price_change_frequency")
    for _, r in snap.iterrows():
        N[f"eda_snap_ratio_{r['state_id']}_{r['category']}"] = r["snap_ratio"]
    foods = snap[snap["category"] == "FOODS"].set_index("state_id")["snap_ratio"]
    nonfoods = snap[snap["category"] != "FOODS"]["snap_ratio"]
    N["eda_snap_foods_max_state"], N["eda_snap_foods_max_ratio"] = foods.idxmax(), float(foods.max())
    N["eda_snap_foods_min_state"], N["eda_snap_foods_min_ratio"] = foods.idxmin(), float(foods.min())
    N["eda_snap_nonfoods_max_ratio"] = float(nonfoods.max())
    ev_e = ev_e[ev_e["n_occurrences"] >= 3].sort_values("avg_ratio_vs_same_weekday_neighbours", ascending=False)
    N["eda_event_top"], N["eda_event_top_ratio"] = ev_e.iloc[0]["event"], ev_e.iloc[0]["avg_ratio_vs_same_weekday_neighbours"]
    N["eda_event_bottom"], N["eda_event_bottom_ratio"] = ev_e.iloc[-1]["event"], ev_e.iloc[-1]["avg_ratio_vs_same_weekday_neighbours"]
    N["eda_event_second_bottom"], N["eda_event_second_bottom_ratio"] = ev_e.iloc[-2]["event"], ev_e.iloc[-2]["avg_ratio_vs_same_weekday_neighbours"]
    N["eda_price_change_week_pct"] = float((pc["price_change_week_pct"] * pc["comparable_weeks"]).sum() / pc["comparable_weeks"].sum() / 100)
    N["eda_price_cut_week_pct"] = float((pc["price_cut_week_pct"] * pc["comparable_weeks"]).sum() / pc["comparable_weeks"].sum() / 100)
    pc_f = pc.set_index("category")["price_change_week_pct"]
    N["eda_price_change_foods_pct"], N["eda_price_change_hobbies_pct"] = float(pc_f["FOODS"] / 100), float(pc_f["HOBBIES"] / 100)

    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8), gridspec_kw={"width_ratios": [1.1, 1.2, 0.8]})
    piv = snap.pivot(index="category", columns="state_id", values="snap_ratio")
    piv.plot.bar(ax=axes[0], color=[cols[c] for c in piv.columns], rot=0, width=0.75)
    axes[0].axhline(1, color="black", ls=":", lw=1); axes[0].set_ylim(0.9, max(1.35, piv.values.max() + 0.03))
    axes[0].set_title("Units on SNAP days vs other days"); axes[0].set_xlabel(""); axes[0].set_ylabel("Ratio (1.00 = same)")
    show = pd.concat([ev_e.head(5), ev_e.tail(5)]).drop_duplicates("event").sort_values("avg_ratio_vs_same_weekday_neighbours")
    axes[1].barh(show["event"], show["avg_ratio_vs_same_weekday_neighbours"],
                 color=[viz.PALETTE["good"] if v >= 1 else viz.PALETTE["bad"] for v in show["avg_ratio_vs_same_weekday_neighbours"]])
    axes[1].axvline(1, color="black", ls=":", lw=1); axes[1].set_xlim(0.6, 1.4)
    axes[1].set_title("Event days: units vs same weekday +/-1 week"); axes[1].set_xlabel("Ratio (1.00 = normal)")
    axes[2].bar(pc["category"].str.title(), pc["price_change_week_pct"] / 100, color=[viz.CAT_COLORS[c] for c in pc["category"]])
    viz.pct_axis(axes[2]); axes[2].set_title("Share of item-store weeks\nwith a price change")
    viz.save(fig, "eda_05_snap_events_price_changes")

    # ------------------------------------------------------------------ 5. intermittency and price levels
    item = kpis.build_item_kpis(panel)
    isk = kpis.build_item_state_kpis(panel, item)
    N["eda_zero_week_pct"] = float(((panel.units == 0) & on).sum() / on.sum())
    N["eda_share_item_state_zero_over_20pct"] = float((isk["zero_week_share"] > 0.20).mean())
    N["eda_share_item_state_zero_over_50pct"] = float((isk["zero_week_share"] > 0.50).mean())
    N["eda_n_item_states"] = len(isk)
    vc = isk["demand_class"].value_counts(normalize=True)
    for k in ("smooth", "intermittent", "erratic", "lumpy"):
        N[f"eda_class_share_{k}"] = float(vc.get(k, 0.0))
    cvb = isk["cv_band"].value_counts(normalize=True)
    for k in ("stable", "variable", "erratic"):
        N[f"eda_cv_share_{k}"] = float(cvb.get(k, 0.0))
    N["eda_cv_median"] = float(isk["cv"].median())
    N["eda_item_max_over_median_units"] = float(item["units"].max() / item["units"].median())
    N["eda_item_median_price"] = float(item["avg_selling_price"].median())
    price_by_cat = item.groupby("cat_id")["avg_selling_price"].agg(["median", "min", "max"])
    price_by_cat.to_csv(cfg.TABLES / "eda_item_price_by_category.csv")
    for c, r in price_by_cat.iterrows():
        N[f"eda_median_price_{c}"] = float(r["median"])

    fig, axes = plt.subplots(1, 3, figsize=(17, 4.8))
    for c in ("FOODS", "HOUSEHOLD", "HOBBIES"):
        axes[0].hist(isk.loc[isk["cat_id"] == c, "zero_week_share"], bins=40, alpha=0.55, color=viz.CAT_COLORS[c], label=c.title())
    axes[0].set_xlim(0, 1); axes[0].set_yscale("log"); viz.pct_axis(axes[0], "x")
    axes[0].set_title("Share of on-sale weeks with zero sales\n(item x state, log count)"); axes[0].legend()
    samp = isk.dropna(subset=["adi", "cv2_nonzero"]).sample(3000, random_state=cfg.SEED)
    for k, col in (("smooth", viz.PALETTE["main"]), ("erratic", viz.PALETTE["accent"]), ("intermittent", viz.PALETTE["good"]), ("lumpy", viz.PALETTE["bad"])):
        s_ = samp[samp["demand_class"] == k]
        axes[1].scatter(s_["adi"], s_["cv2_nonzero"].clip(lower=1e-3), s=8, alpha=0.5, color=col, label=k)
    axes[1].axvline(cfg.ADI_CUTOFF, color="black", ls="--", lw=1); axes[1].axhline(cfg.CV2_CUTOFF, color="black", ls="--", lw=1)
    axes[1].set_xscale("log"); axes[1].set_yscale("log"); axes[1].set_xlabel("ADI (weeks between sales)"); axes[1].set_ylabel("CV^2 of non-zero weeks")
    axes[1].set_title("Demand classes (3,000 random item-states)"); axes[1].legend(fontsize=8)
    for c in ("FOODS", "HOUSEHOLD", "HOBBIES"):
        axes[2].boxplot(item.loc[item["cat_id"] == c, "avg_selling_price"], positions=[["FOODS", "HOUSEHOLD", "HOBBIES"].index(c)], widths=0.6,
                        patch_artist=True, boxprops=dict(facecolor=viz.CAT_COLORS[c], alpha=0.6), showfliers=False)
    axes[2].set_xticks([0, 1, 2]); axes[2].set_xticklabels(["Foods", "Household", "Hobbies"]); axes[2].set_yscale("log")
    axes[2].set_title("Item average selling price ($, log scale)")
    viz.save(fig, "eda_06_intermittency_and_price")

    nums.save(N)
    for k, v in N.items():
        print(f"{k:<40} {v}")


if __name__ == "__main__":
    main()
