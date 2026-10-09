"""
Step 8 - turn findings into business recommendations.

Every sentence below is built from numbers saved by steps 5-7 (key_numbers.json) or recomputed from the
cleaned data. Nothing is typed by hand: re-run the pipeline with other data and the text updates itself.

Writes outputs/tables/recommendations.csv and outputs/recommendations.md, adds numbers to key_numbers.json.
Run:  python src/08_recommendations.py
"""
import numpy as np
import pandas as pd

import config as cfg
import keynums as nums
import kpis

BASELINE_KEY = {"Naive (last week)": "naive", "Moving average": "ma", "Exp. smoothing": "ses"}


def usd(x):
    return f"${x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"${x / 1e3:,.0f}K"


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def main():
    cfg.ensure_dirs()
    t = kpis.load_clean()
    N = nums.load()
    pol = pd.read_csv(cfg.TABLES / "kpi_policy_check.csv")
    lt_sup = pd.read_csv(cfg.TABLES / "kpi_lead_time_supplier.csv")
    seas = pd.read_csv(cfg.TABLES / "eda_seasonality_index.csv", index_col=0)
    cl = pd.read_csv(cfg.TABLES / "cleaning_log.csv")
    X = {}

    # ---- extra numbers needed only here
    d = t["demand_daily"]
    pr = d.groupby("promo_flag")["stockout_flag"].mean()
    X["rec_stockout_promo"], X["rec_stockout_normal"] = pr.loc[1], pr.loc[0]

    # phase-1 target: the 20 SKU-warehouses that lost the most revenue in the last 13 weeks
    top20 = pol.sort_values("recent_lost_revenue", ascending=False).head(20)
    X["rec_phase1_n"] = len(top20)
    X["rec_phase1_lost_rev"] = top20["recent_lost_revenue"].sum()
    X["rec_phase1_invest"] = top20["extra_inventory_value_needed"].sum()
    X["rec_phase1_share_of_recent_loss"] = X["rec_phase1_lost_rev"] / pol["recent_lost_revenue"].sum()
    X["rec_phase1_invest_pct_inventory"] = X["rec_phase1_invest"] / N["kpi_avg_inventory_value"]
    X["rec_suppliers_below_50"] = int((lt_sup["on_time_rate"] < 0.5).sum())
    X["rec_suppliers_total"] = len(lt_sup)
    most = seas.loc[N["eda_most_seasonal_category"]]
    X["rec_season_peak_month"], X["rec_season_peak_idx"] = most.idxmax(), most.max()
    X["rec_season_low_month"], X["rec_season_low_idx"] = most.idxmin(), most.min()
    X["rec_cleaning_rows_fixed"] = int(cl.loc[~cl["issue"].str.contains("check only|integrity", case=False), "rows_affected"].sum())
    fills = [N["abc_a_fill"], N["abc_b_fill"], N["abc_c_fill"]]
    X["rec_abc_fill_spread_pp"] = (max(fills) - min(fills)) * 100
    N.update(X)

    recs = []

    def add(area, finding, action, kpi, value=np.nan, basis=""):
        recs.append(dict(area=area, finding=finding, action=action, kpi_to_track=kpi,
                         value_at_stake_usd=value, value_basis=basis))

    add("Fix the top lost-revenue SKUs first",
        f"The top 15 SKUs account for {pct(N['kpi_top15_lost_share'], 0)} of all lost revenue ({N['kpi_top15_a_count']} of them are A items); "
        f"the worst is {N['kpi_top_lost_sku']} with {usd(N['kpi_top_lost_sku_value'])}.",
        "Run a weekly stockout review on these 15 SKUs: confirm lead time, check open POs, raise reorder points before touching the long tail.",
        "Lost revenue of top-15 SKUs", N["kpi_lost_revenue"] * N["kpi_top15_lost_share"], "lost revenue, whole period")

    add("Reorder policy refresh",
        f"Fill rate {'fell' if N['kpi_fill_last_3m'] < N['kpi_fill_first_3m'] else 'rose'} from {pct(N['kpi_fill_first_3m'])} (first 3 months) to {pct(N['kpi_fill_last_3m'])} (last 3 months) "
        f"while demand grew {pct(N['eda_yoy_growth_total'])} year on year. {N['pol_under_n']} of {N['pol_n_sku_wh']} SKU-warehouses ({pct(N['pol_under_share'], 0)}) have a reorder "
        f"point below what current demand and actual lead times require; they run a {pct(N['pol_stockout_under'])} stockout-day rate vs {pct(N['pol_stockout_ok'])} for the rest.",
        f"Re-calculate safety stock and reorder point every quarter from the last 13 weeks of demand and the supplier's ACTUAL lead time and its variability. "
        f"Phase 1: the {N['rec_phase1_n']} SKU-warehouses that lost the most revenue in the last 13 weeks ({usd(N['rec_phase1_lost_rev'])}, {pct(N['rec_phase1_share_of_recent_loss'], 0)} of the total) "
        f"need about {usd(N['rec_phase1_invest'])} of extra safety stock ({pct(N['rec_phase1_invest_pct_inventory'], 0)} of today's average inventory value).",
        "Fill rate, stockout-day rate, inventory turnover", N["pol_recent_lost_revenue_total"], "lost revenue, last 13 weeks")

    add("ABC-differentiated service levels",
        f"A items are {pct(N['abc_a_sku_share'], 0)} of SKUs but {pct(N['abc_a_revenue_share'], 0)} of revenue and {pct(N['abc_a_lost_revenue_share'], 0)} of lost revenue, yet their fill rate "
        f"({pct(N['abc_a_fill'])}) is within {N['rec_abc_fill_spread_pp']:.1f} percentage points of C items ({pct(N['abc_c_fill'])}): every SKU gets the same service-level target.",
        f"Set service targets by class (for example 98% for A, 95% for B, 90% for C). C items hold only {pct(N['abc_c_inventory_share'])} of inventory value, "
        "so the extra A-item stock has to be budgeted, not funded by trimming C.",
        "Fill rate by ABC class, lost revenue in class A", N["abc_a_lost_revenue"], "A-class lost revenue, whole period")

    add("Supplier lead-time reliability",
        f"Only {pct(N['lt_on_time_rate'])} of delivered POs arrive on or before the promised date; late POs are {N['lt_avg_delay_when_late']:.1f} days late on average. "
        f"On-time rate ranges from {pct(N['lt_worst_supplier_on_time'])} ({N['lt_worst_supplier']}) to {pct(N['lt_best_supplier_on_time'])} ({N['lt_best_supplier']}); "
        f"{N['rec_suppliers_below_50']} of {N['rec_suppliers_total']} suppliers are below 50% on-time.",
        "Start a monthly supplier scorecard (on-time %, delay days, lead-time CV), escalate the bottom suppliers, and use measured lead time + variability (not the quoted lead time) in safety-stock formulas.",
        "On-time delivery %, lead-time CV by supplier")

    add("Expediting cost",
        f"{pct(N['lt_air_po_share'], 0)} of POs ship by air at {pct(N['lt_air_freight_pct'])} of goods value vs {pct(N['lt_nonair_freight_pct'])} for other modes - "
        f"about {usd(N['lt_air_extra_freight'])} of extra freight over the period.",
        "Fewer emergency orders: earlier reorder triggers (see policy refresh) are cheaper than air freight. Review air shipments by SKU and keep air only for A items.",
        "Air-freight share of POs, freight % of PO value", N["lt_air_extra_freight"], "extra freight vs non-air rates, whole period")

    add("Promotion planning",
        f"Promo weeks run at {N['eda_promo_ratio']:.2f}x the previous 8-week average (normal weeks {N['eda_normal_ratio']:.2f}x). Stockout rate on promo days is "
        f"{pct(N['rec_stockout_promo'])} vs {pct(N['rec_stockout_normal'])} on normal days.",
        "Share the promotion calendar with planning and add the promo flag to the forecast (it is the planned, known input the baselines ignore). Build stock one lead time BEFORE a promo.",
        "Stockout rate on promo days")

    add("Seasonal stock planning",
        f"{N['eda_most_seasonal_category']} swings {N['eda_most_seasonal_swing']:.2f} index points between its peak ({N['rec_season_peak_month']}, {N['rec_season_peak_idx']:.2f}) "
        f"and low ({N['rec_season_low_month']}, {N['rec_season_low_idx']:.2f}) month; category peaks fall in different months.",
        "Adjust reorder points by the monthly seasonal index, so stock is built ahead of each category's peak rather than a flat yearly parameter.",
        "Fill rate in peak months by category")

    bk = BASELINE_KEY[N["fc_best_baseline"]]
    verdict_txt = {"NN_WINS": "beats the best baseline", "MARGINAL": "beats the best baseline only marginally",
                   "BASELINE_WINS": "does not beat the best baseline"}[N["fc_verdict"]]
    add("Forecasting model choice",
        f"On the untouched test weeks the best baseline ({N['fc_best_baseline']}) has WAPE {pct(N['fc_wape_test_' + bk])}, "
        f"linear regression {pct(N['fc_wape_test_linear'])} and the MLP {pct(N['fc_wape_test_mlp'])}. The MLP {verdict_txt}, "
        f"but adds only {pct(N['fc_mlp_rel_gain_vs_linear_test'])} relative improvement over linear regression. Chosen model: {N['fc_final_model']}.",
        f"Use {N['fc_final_model']} for weekly forecasts (promo flag + recent demand + month), keep the {N['fc_best_baseline']} as the fallback and the MLP as a challenger to re-test each quarter.",
        "WAPE, bias on a rolling basis")

    add("Forecast accuracy -> safety stock",
        f"Using the MLP's forecast errors instead of the {N['fc_best_baseline']}'s changes the indicative safety-stock requirement by {pct(N['ss_pct_change_mlp_vs_baseline'])} "
        f"({usd(N['ss_value_baseline'])} -> {usd(N['ss_value_mlp'])}).",
        "Size safety stock from forecast error (not raw demand variability) once the forecast is live; track the realised error each month.",
        "Forecast error std per SKU, safety-stock value")

    add("Data quality at the source",
        f"Cleaning corrected or removed {N['rec_cleaning_rows_fixed']:,} records (duplicates, impossible values, mixed formats).",
        "Add input validation in the ERP export: unique keys, non-negative quantities, ISO dates, controlled category lists.",
        "Rows rejected by validation per load")

    # priority = analyst judgement (size of lost revenue x how quickly it can be acted on) = order of the list above
    df = pd.DataFrame(recs)
    df.insert(0, "priority", np.arange(1, len(df) + 1))
    df.to_csv(cfg.TABLES / "recommendations.csv", index=False)

    lines = ["# Business recommendations (generated from the data)\n"]
    for _, r in df.iterrows():
        val = f" | Value at stake: {usd(r['value_at_stake_usd'])} ({r['value_basis']})" if pd.notna(r["value_at_stake_usd"]) else ""
        lines += [f"### {r['priority']}. {r['area']}{val}", f"**Finding:** {r['finding']}\n", f"**Action:** {r['action']}\n", f"**Track:** {r['kpi_to_track']}\n"]
    (cfg.OUTPUTS / "recommendations.md").write_text("\n".join(lines), encoding="utf-8")
    X["rec_count"] = len(df)
    nums.save(X)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
