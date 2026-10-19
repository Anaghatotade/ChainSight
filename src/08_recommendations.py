"""
Step 8 - turn findings into business recommendations.

Every sentence below is built from numbers saved by steps 2-7 (key_numbers.json) or from the output tables.
Nothing is typed by hand: re-run the pipeline and the text updates itself.

Honesty rule: the M5 data has NO inventory, stockout, cost or lead-time data. So the recommendations are about
demand, assortment, calendar effects and forecasting - things the data can really support. The two that use an
assumed lead time (safety stock, policy simulation) say so in their own text.

Writes outputs/tables/recommendations.csv and outputs/recommendations.md, adds numbers to key_numbers.json.
Run:  python src/08_recommendations.py
"""
import math

import numpy as np
import pandas as pd

import config as cfg
import keynums as nums

BASELINE_KEY = {"Naive (last week)": "naive", "Moving average": "ma", "Exp. smoothing": "ses"}


def usd(x):
    return f"${x / 1e6:,.1f}M" if abs(x) >= 1e6 else f"${x / 1e3:,.0f}K"


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def service_from_z(z):
    """Cycle service level implied by a safety factor z (standard normal CDF)."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def main():
    cfg.ensure_dirs()
    N = nums.load()
    T = cfg.TABLES
    X = {}

    # ---- numbers needed only here (computed from output tables, not typed)
    abc = pd.read_csv(T / "kpi_abc_summary.csv").set_index("abc_class")
    X["rec_C_zero_week_share"], X["rec_A_zero_week_share"] = abc.loc["C", "zero_week_share"], abc.loc["A", "zero_week_share"]
    cls = pd.read_csv(T / "kpi_demand_class_summary.csv").set_index("demand_class")
    X["rec_nonsmooth_ss_share"] = N["pol_erratic_ss_share"]
    cv_band = pd.read_csv(T / "kpi_policy_assumed_by_cv_band.csv").set_index("cv_band")
    X["rec_erratic_weeks_cover"], X["rec_stable_weeks_cover"] = cv_band.loc["erratic", "median_weeks_of_cover"], cv_band.loc["stable", "median_weeks_of_cover"]
    ev = pd.read_csv(cfg.SQL_RESULTS / "05_price_and_events__event_uplift_by_event.csv")
    X["rec_n_events_above_105"] = int((ev["avg_ratio_vs_same_weekday_neighbours"] >= 1.05).sum())
    X["rec_n_events_below_95"] = int((ev["avg_ratio_vs_same_weekday_neighbours"] <= 0.95).sum())
    X["rec_n_events"] = len(ev)
    seg = pd.read_csv(T / "forecast_segment_wape.csv")
    cat_t = seg[(seg["split"] == "test") & (seg["segment_type"] == "category")].set_index("segment")
    X["rec_mlp_gain_hobbies"] = 1 - cat_t.loc["HOBBIES", "WAPE_mlp"] / cat_t.loc["HOBBIES", "WAPE_baseline"]
    X["rec_mlp_gain_foods"] = 1 - cat_t.loc["FOODS", "WAPE_mlp"] / cat_t.loc["FOODS", "WAPE_baseline"]
    X["rec_decay_per_year"] = -N["eda_lfl_growth_total"]
    bk = BASELINE_KEY[N["fc_best_baseline"]]

    # why the simulated stock gap is bigger than the WAPE gap: safety stock follows the SPREAD of forecast errors (std),
    # valued at price, and that spread differs more between the models than WAPE does (dev weeks, as in the simulation)
    pred = pd.read_csv(cfg.DATA_PROCESSED / "forecast_predictions.csv.gz", usecols=["series", "split", "actual", "price", bk, "mlp"])
    dev, test = pred[pred["split"] == "dev"], pred[pred["split"] == "test"]
    spread = pd.DataFrame({m: (dev[m] - dev["actual"]).groupby(dev["series"]).std(ddof=0) for m in (bk, "mlp")})
    value = spread.mul(test.groupby("series")["price"].mean(), axis=0).dropna().sum()
    X["rec_error_spread_value_change_mlp"] = value["mlp"] / value[bk] - 1
    N.update(X)
    verdict_txt = {"NN_WINS": "beats the best baseline", "MARGINAL": "is slightly better than the best baseline but misses the bar we set in advance",
                   "BASELINE_WINS": "does not beat the best baseline"}[N["fc_verdict"]]

    recs = []

    def add(area, finding, action, kpi, value=np.nan, basis="", evidence="measured"):
        recs.append(dict(area=area, evidence=evidence, finding=finding, action=action, kpi_to_track=kpi,
                         value_at_stake_usd=value, value_basis=basis))

    add("Plan by ABC class: put the effort where the revenue is",
        f"{N['kpi_abc_A_n']:,} A items ({pct(N['kpi_abc_A_items_share'], 0)} of items) make {pct(N['kpi_abc_A_revenue_share'], 0)} of revenue; "
        f"the {N['kpi_abc_C_n']:,} C items ({pct(N['kpi_abc_C_items_share'], 0)}) make only {pct(N['kpi_abc_C_revenue_share'], 0)}. "
        f"The single best item ({N['kpi_top_item']}) is {usd(N['kpi_top_item_revenue'])}, but the top 100 items are only {pct(N['kpi_top100_items_revenue_share'], 0)} of revenue: "
        "this is a long, flat catalogue, not a handful of stars.",
        "Review A items weekly with a tight service target, B items every 2-4 weeks, and manage C items by exception. "
        "Because 'A' is a wide group here, split it again by demand variability (ABC x CV matrix) before setting stock rules.",
        "Revenue and zero-sales weeks by ABC class", N["kpi_total_revenue"] * N["kpi_abc_A_revenue_share"], "revenue of A items, whole period")

    add("Rationalise the slow tail",
        f"{N['kpi_slow_C_n']} C items ({pct(N['kpi_slow_C_share_of_C_items'], 0)} of all C items) are slow movers (no sale in more than {pct(cfg.SLOW_ZERO_SHARE, 0)} of their listed weeks) with only {pct(N['kpi_slow_C_revenue_share'], 1)} of total revenue. "
        f"C items have no sale in {pct(N['rec_C_zero_week_share'], 0)} of the weeks they are listed, vs {pct(N['rec_A_zero_week_share'], 0)} for A items.",
        "Review these slow C items for delisting or for a lower store footprint, and stock the rest to order-on-demand or larger, less frequent batches. "
        "Check first that they are not enablers (basket items) the data cannot show.",
        "Share of listed weeks with zero sales; revenue per listed item", N["kpi_total_revenue"] * N["kpi_slow_C_revenue_share"], "revenue of the slow C items (what a delisting would put at risk)")

    add("Safety stock by item class (assumption-based)",
        f"ASSUMPTION: 1-week lead time and review, 95% cycle service (config.py). On the real demand variability this implies about {usd(N['pol_ss_retail_value'])} of safety stock at retail value "
        f"for {N['pol_n_item_states']:,} item-state series; A items hold {pct(N['pol_ss_value_A_share'], 0)} of it. "
        f"Erratic series are {pct(N['pol_erratic_item_share'], 0)} of series but need {pct(N['pol_erratic_ss_share'], 0)} of the safety stock "
        f"(median cover {N['rec_erratic_weeks_cover']:.1f} weeks vs {N['rec_stable_weeks_cover']:.1f} for stable series). "
        f"Giving A / B / C different service targets ({pct(service_from_z(cfg.SERVICE_Z_BY_CLASS['A']), 0)} / {pct(service_from_z(cfg.SERVICE_Z_BY_CLASS['B']), 0)} / {pct(service_from_z(cfg.SERVICE_Z_BY_CLASS['C']), 0)}) changes the total by {pct(N['pol_ss_change_by_class'], 1)}.",
        "Replace one flat service factor by class- and variability-specific factors, and replace the lead-time assumption with real supplier lead times as soon as they are available.",
        "Safety-stock weeks of cover by class", N["pol_ss_retail_value"], "safety stock at retail value (assumption-based)", evidence="assumption-based")

    add("Plan around the calendar: SNAP days, events, weekdays",
        f"In FOODS, SNAP benefit days lift units to {N['eda_snap_foods_min_ratio']:.2f}x ({N['eda_snap_foods_min_state']}) up to {N['eda_snap_foods_max_ratio']:.2f}x ({N['eda_snap_foods_max_state']}) "
        f"of non-SNAP days; the effect on other categories is at most {N['eda_snap_nonfoods_max_ratio']:.2f}x. "
        f"{N['rec_n_events_above_105']} of {N['rec_n_events']} named events sell at least 5% above normal neighbouring days (best: {N['eda_event_top']}, {N['eda_event_top_ratio']:.2f}x) "
        f"and {N['rec_n_events_below_95']} at least 5% below (lowest: {N['eda_event_bottom']}, {N['eda_event_bottom_ratio']:.2f}x). "
        f"{N['eda_weekday_peak']} is {N['eda_weekday_peak_vs_trough']:.2f}x the lowest weekday ({N['eda_weekday_trough']}).",
        "Load the state-specific SNAP calendar, the event calendar and a weekday profile into replenishment and staffing plans, and build stock for FOODS ahead of SNAP days state by state.",
        "Units on SNAP vs non-SNAP days by state", None, "")

    add("Seasonal stock planning",
        f"{N['eda_most_seasonal_dept']} swings {N['eda_most_seasonal_swing']:.2f} index points between its peak ({N['eda_most_seasonal_peak_month']}, {N['eda_most_seasonal_peak_index']:.2f}) "
        f"and low ({N['eda_most_seasonal_trough_month']}, {N['eda_most_seasonal_trough_index']:.2f}) month; the three categories swing only "
        f"{N['eda_swing_FOODS']:.2f} (FOODS), {N['eda_swing_HOUSEHOLD']:.2f} (HOUSEHOLD) and {N['eda_swing_HOBBIES']:.2f} (HOBBIES) overall, with peaks in {N['eda_peak_month_FOODS']}, "
        f"{N['eda_peak_month_HOUSEHOLD']} and {N['eda_peak_month_HOBBIES']}.",
        "Apply monthly seasonal indices at department level instead of a flat yearly parameter, starting with the most seasonal department.",
        "Forecast bias by month")

    add("Price cuts: test before you scale",
        f"Price-cut weeks are rare ({pct(N['kpi_pcu_cut_share'], 2)} of item-state weeks). In those weeks the typical item sells {N['kpi_pcu_cut_median_ratio']:.2f}x its previous 8-week average "
        f"(normal weeks {N['kpi_pcu_normal_median_ratio']:.2f}x) - but the mean is {N['kpi_pcu_cut_mean_ratio']:.2f}x, so the average is pulled up by a few items that jump a lot. "
        "This is an association: cuts may be timed with seasons and events.",
        "Run a controlled price test (similar stores, with and without the cut) before basing a stock-up rule on this uplift; when a cut is planned, add it to the forecast as a known input.",
        "Unit uplift in test vs control stores")

    add("Forecasting model choice",
        f"On the untouched test weeks the best baseline ({N['fc_best_baseline']}) has WAPE {pct(N['fc_wape_test_' + bk])}, linear regression {pct(N['fc_wape_test_linear'])} "
        f"and the MLP {pct(N['fc_wape_test_mlp'])}. The MLP {verdict_txt} ({pct(N['fc_mlp_rel_gain_vs_baseline_test'])} relative gain; required: {pct(cfg.MIN_RELATIVE_GAIN, 0)}). "
        f"Chosen model: {N['fc_final_model']}.",
        f"Use {N['fc_final_model']} for weekly forecasts; keep the MLP as a challenger and re-test it each quarter, and look for new information (price plans, events, stock availability) rather than a bigger network.",
        "WAPE and bias, rolling")

    add("What forecast accuracy could mean for stock (simulation, assumption-based)",
        f"ASSUMPTION: 1-week lead and review period. In a replay of the real test weeks, a policy using the MLP forecast reaches {pct(cfg.FILL_RATE_TARGET, 0)} fill with "
        f"{usd(N['sim_inv_at_target_mlp'])} of average inventory vs {usd(N['sim_inv_at_target_' + bk])} for the {N['fc_best_baseline']} policy ({pct(N['sim_mlp_inventory_change_vs_baseline'])} change). "
        f"That is a bigger gap than the {pct(N['fc_mlp_rel_gain_vs_baseline_test'])} WAPE gap, because safety stock follows the spread of forecast errors (retail-value weighted, the MLP's spread is "
        f"{pct(abs(N['rec_error_spread_value_change_mlp']))} {'lower' if N['rec_error_spread_value_change_mlp'] < 0 else 'higher'}). Treat it as indicative, not as a result: it depends on the assumed lead time and on observed sales being true demand (lost sales are invisible).",
        "Do not switch models on this alone. If a pilot with real stock and lead-time data shows a similar gap, the MLP's small accuracy edge would be worth its extra effort.",
        "Inventory needed for a target fill rate", abs(N["sim_inv_at_target_mlp"] - N["sim_inv_at_target_" + bk]), "difference in average inventory (simulation)", evidence="assumption-based")

    add("Close the data gap: record stock and stockouts",
        f"{pct(N['dq_not_on_sale_share'], 0)} of item-store-weeks have no price (item not yet on sale); {pct(N['eda_zero_week_pct'], 0)} of listed weeks have zero sales, "
        "and with no stock-on-hand data a zero cannot be told apart from a stockout. So fill rate, turnover and days of inventory cannot be measured from this data.",
        "Capture weekly on-hand stock, stockout flags, purchase prices and supplier lead times next to the sales data; with them the service and inventory KPIs become measurable.",
        "Share of sales rows with stock-on-hand recorded")

    df = pd.DataFrame(recs)
    df.insert(0, "priority", np.arange(1, len(df) + 1))
    df.to_csv(T / "recommendations.csv", index=False)

    lines = ["# Business recommendations (generated from the data)\n",
             "_Evidence: **measured** = computed from the real M5 data; **assumption-based** = uses an assumed lead time (see config.py)._\n"]
    for _, r in df.iterrows():
        val = f" | Value at stake: {usd(r['value_at_stake_usd'])} ({r['value_basis']})" if pd.notna(r["value_at_stake_usd"]) else ""
        lines += [f"### {r['priority']}. {r['area']}{val}", f"_Evidence: {r['evidence']}_\n", f"**Finding:** {r['finding']}\n",
                  f"**Action:** {r['action']}\n", f"**Track:** {r['kpi_to_track']}\n"]
    (cfg.OUTPUTS / "recommendations.md").write_text("\n".join(lines), encoding="utf-8")
    nums.save({**X, "rec_count": len(df)})
    print("\n".join(lines))


if __name__ == "__main__":
    main()
