# ChainSight - Retail Demand & Inventory Analytics on real Walmart data (Data Analyst / Business Analyst portfolio project)

> **One line:** I took the real Kaggle **M5 (Walmart)** sales data - {{data_n_items:int}} items, {{data_n_stores}} stores, {{data_n_weeks}} weeks - cleaned and validated it, measured demand and revenue KPIs in SQL and pandas, forecast weekly demand (simple baselines first, a small neural network only as a challenger) and ended with prioritised, evidence-labelled recommendations.

**Story:** raw data -> cleaning -> EDA -> KPI analysis -> inventory / demand insights -> forecasting (baselines vs a simple neural network) -> business recommendations.

> **Data note:** the data is **real**: Kaggle *M5 Forecasting - Accuracy* (Walmart US, {{data_start_date}} to {{data_end_date}}). It is not committed here (Kaggle competition rules); see `README_SETUP.md` for how to download it. Every number below is produced by the code and written into this file by `src/10_render_docs.py` - nothing is typed by hand. M5 has **no inventory, stock-out, cost or lead-time data**, so service KPIs (fill rate, turnover, days of inventory) are **not** computed; the two sections that need a lead time are explicitly marked **assumption-based**.

---

## 1. Executive summary (the "so what" first)

| | |
|---|---|
| **Scale** | {{data_total_units:int}} units and **{{data_total_revenue:usd}}** revenue (units x weekly price) over {{data_n_weeks}} full weeks, {{data_n_items:int}} items in {{data_n_categories}} categories, {{data_n_stores}} stores in {{data_n_states}} states |
| **Concentration** | {{kpi_abc_A_n:int}} **A items** ({{kpi_abc_A_items_share:pct0}} of items) make {{kpi_abc_A_revenue_share:pct0}} of revenue; the top 100 items are only {{kpi_top100_items_revenue_share:pct0}} - a long, flat catalogue |
| **Growth** | {{growth_phrase}} |
| **Calendar drives demand** | FOODS sells {{eda_snap_foods_min_ratio:x2}} ({{eda_snap_foods_min_state}}) to {{eda_snap_foods_max_ratio:x2}} ({{eda_snap_foods_max_state}}) as much on SNAP days; {{eda_weekday_peak}} is {{eda_weekday_peak_vs_trough:x2}} the lowest weekday; {{eda_most_seasonal_dept}} swings {{eda_most_seasonal_swing:f2}} index points over the year |
| **Intermittency** | {{eda_zero_week_pct:pct0}} of listed item-store-weeks have zero sales; {{kpi_slow_C_n}} slow C items ({{kpi_slow_C_revenue_share:pct1}} of revenue) are candidates for range review |
| **Forecasting verdict** | {{verdict_text}} {{final_text}} |
| **What the data cannot say** | Fill rate, stock-outs, turnover and days of inventory need stock data that M5 does not have; a zero-sales week cannot be told apart from a stock-out. The safety-stock numbers use an **assumed** {{pol_lead_time_weeks}}-week lead time |

![Weekly trend](outputs/charts/eda_01_weekly_trend.png)

**Top recommendations** (full list with numbers in section 6):

1. Plan by ABC class and split the wide A group by demand variability.
2. Review the {{kpi_slow_C_n}} slow C items for delisting or smaller footprint.
3. Put SNAP days, events and weekday patterns into replenishment plans, state by state.
4. Use **{{fc_final_model}}** for weekly forecasts; keep the neural network as a quarterly challenger.
5. Start recording stock-on-hand and stock-outs - the data gap is what stops service KPIs.

---

## 2. Problem and questions

A regional retailer sells {{data_n_items:int}} items through {{data_n_stores}} stores. Management asks:

1. Which items and categories carry the business, and how concentrated is it (ABC)?
2. How does demand move - trend, seasonality, weekday, holidays, SNAP benefit days, price changes?
3. Which items are easy or hard to predict (variability, intermittency)?
4. What safety stock would a reorder policy need, *if* lead times were as assumed?
5. Can we forecast weekly demand better than simple rules - and is a neural network worth its complexity?

### What this data can and cannot answer

| Question | Answerable from M5? |
|---|---|
| Revenue, units, price, ABC, demand variability, intermittency | **Yes - measured** |
| Trend, seasonality, weekday, events, SNAP effect, price-cut association | **Yes - measured** (associations, not causal effects) |
| Forecast accuracy of baselines vs linear vs MLP | **Yes - measured** on a time-based hold-out |
| Safety stock / reorder point | **Only with an assumed lead time** (`config.py`) - labelled "assumption-based" everywhere |
| Fill rate, stock-out rate, turnover, days of inventory, supplier reliability, margin | **No** - M5 has no stock, cost or supplier data |

## 3. Dataset

Kaggle *M5 Forecasting - Accuracy* (Makridakis, Spiliotis, Assimakopoulos, "The M5 accuracy competition: Results, findings and conclusions", *International Journal of Forecasting*, 2022). Three raw files used (checksums so anyone can verify they have the same data):

{{@table:raw_files}}

| Table | Grain | Rows (raw) |
|---|---|---|
| `sales_train_validation` | item x store, one column per day (wide) | {{data_n_sales_rows_raw:int}} series x {{data_n_days_raw}} days |
| `sell_prices` | item x store x week | {{data_n_price_rows_raw:int}} |
| `calendar` | one row per day (weekday, month, events, SNAP flags) | 1,969 days |

There is no price for a week before an item's first listing: the zeros before launch are **not demand** and are masked (see 4.1). See `docs/DATA_DICTIONARY.md`.

## 4. Approach and key findings (each step ends with a "so what")

### 4.1 Cleaning and validation (`src/cleaning.py`, `notebooks/01_cleaning.ipynb`)
Honest finding: the real data is much cleaner than a typical business extract - no duplicates, no negatives, no missing sales. The work is **structural**: prove the data is what the documentation says, drop the {{dq_dropped_days}} trailing days that do not make a full week, and **mask {{dq_not_on_sale_share:pct0}} of series-weeks** where the item had no price (not yet on sale), so they are not counted as zero demand. {{dq_price_jumps:int}} week-to-week price changes above 3x and {{dq_spike_weeks:int}} demand spikes are *flagged, never deleted* (holiday peaks are exactly what a forecast must handle).

{{@table:data_quality_summary}}

**Independent check** (`src/verify_against_raw.py`): units and revenue were recomputed for each of the {{verify_n_stores}} stores straight from the raw files with a different method (long-format merge, none of the cleaning code). Units match for all stores: {{verify_all_units_match}}; largest store-level revenue difference ${{verify_max_store_revenue_diff:f2}}; total {{verify_total_revenue:usd}}.

*So what:* treating pre-launch zeros as demand would have made {{dq_not_on_sale_share:pct0}} of the history fake and pulled every average and forecast down; the full rule list is in `outputs/tables/cleaning_log.csv`.

### 4.2 EDA (`src/05_eda.py`, `notebooks/02_eda.ipynb`)

![Assortment and yearly growth](outputs/charts/eda_02_assortment_and_yearly_growth.png)

- **Growth and assortment.** {{growth_phrase}}
- **Mix:** FOODS {{eda_cat_share_FOODS:pct0}} of revenue, HOUSEHOLD {{eda_cat_share_HOUSEHOLD:pct0}}, HOBBIES {{eda_cat_share_HOBBIES:pct0}}; the biggest department is {{eda_top_dept}} ({{eda_top_dept_share:pct0}}). {{eda_top_state}} is {{eda_top_state_share:pct0}} of revenue; the largest store ({{eda_top_store}}) is {{eda_store_top_vs_bottom:f1}}x the smallest ({{eda_bottom_store}}).

![Category, department, store](outputs/charts/eda_03_category_dept_store_mix.png)

- **Seasonality** (complete years {{eda_seasonality_years}}): most seasonal department {{eda_most_seasonal_dept}} (peak {{eda_most_seasonal_peak_month}} {{eda_most_seasonal_peak_index:f2}}, trough {{eda_most_seasonal_trough_month}} {{eda_most_seasonal_trough_index:f2}}); the three categories are far flatter ({{eda_swing_FOODS:f2}} / {{eda_swing_HOUSEHOLD:f2}} / {{eda_swing_HOBBIES:f2}} swing). **Weekday:** {{eda_weekday_peak}} {{eda_weekday_peak_index:f2}}x vs {{eda_weekday_trough}} {{eda_weekday_trough_index:f2}}x.

![Seasonality and weekday](outputs/charts/eda_04_seasonality_and_weekday.png)

- **SNAP days and events:** FOODS units on SNAP days are {{eda_snap_foods_min_ratio:x2}} to {{eda_snap_foods_max_ratio:x2}} of other days ({{snap_phrase}} state-dependent), other categories at most {{eda_snap_nonfoods_max_ratio:x2}}. Events compared with the same weekday a week before and after: best {{eda_event_top}} ({{eda_event_top_ratio:x2}}), lowest {{eda_event_bottom}} ({{eda_event_bottom_ratio:x2}}). SNAP days fall early in the month, so part of that effect is the normal start-of-month pattern.

![SNAP, events, price changes](outputs/charts/eda_05_snap_events_price_changes.png)

- **Intermittent demand:** {{eda_zero_week_pct:pct0}} of listed item-store-weeks have no sale; at item x state level {{eda_share_item_state_zero_over_20pct:pct0}} of series have zero sales in over 20% of their weeks. By demand class: {{eda_class_share_smooth:pct0}} smooth, {{eda_class_share_intermittent:pct0}} intermittent, {{eda_class_share_erratic:pct0}} erratic, {{eda_class_share_lumpy:pct0}} lumpy.

![Intermittency and price](outputs/charts/eda_06_intermittency_and_price.png)

*So what:* one flat parameter per item cannot fit a business whose demand depends on the day of the week, the SNAP calendar, holidays and (for some departments) the season.

### 4.3 KPI analysis (`src/kpis.py`, `src/06_kpi_analysis.py`, `sql/`)

| KPI (measured) | Value |
|---|---|
| Units sold | {{kpi_total_units:int}} |
| Revenue (units x price) | {{kpi_total_revenue:usd}} |
| Average selling price | ${{kpi_avg_selling_price:f2}} |
| Zero-sales share of listed item-store-weeks | {{eda_zero_week_pct:pct1}} |
| Median weekly demand CV (item x state) | {{eda_cv_median:f2}} ({{eda_cv_share_stable:pct0}} stable, {{eda_cv_share_variable:pct0}} variable, {{eda_cv_share_erratic:pct0}} erratic) |

**ABC analysis** (A = first {{abc_a_cut_pct}} of revenue, B = next {{abc_b_cut_pct}}, C = the rest):

![ABC pareto](outputs/charts/kpi_01_pareto_abc.png)

{{@table:kpi_abc_summary|abc_class,n_items,revenue,zero_week_share,items_share,revenue_share}}

A items sell in most weeks ({{kpi_abc_A_zero_week_share:pct0}} zero-sales weeks) while C items often do not ({{kpi_abc_C_zero_week_share:pct0}}). {{kpi_slow_C_n}} C items ({{kpi_slow_C_share_of_C_items:pct0}} of C) are slow movers with only {{kpi_slow_C_revenue_share:pct1}} of revenue. Within A, {{kpi_A_stable_revenue_share:pct0}} of total revenue is stable demand, {{kpi_A_variable_revenue_share:pct0}} variable and {{kpi_A_erratic_revenue_share:pct0}} erratic (ABC x variability matrix).

![ABC x variability](outputs/charts/kpi_02_abc_variability_matrix.png)

**Demand classes** (Syntetos-Boylan): {{kpi_class_smooth_item_share:pct0}} of item-state series are smooth and hold {{kpi_class_smooth_revenue_share:pct0}} of revenue; the {{kpi_nonsmooth_item_share:pct0}} that are not smooth hold {{kpi_nonsmooth_revenue_share:pct0}}.

![Demand classes](outputs/charts/kpi_03_demand_classes.png)

**Price cuts** (week price <= {{pcu_cut_ratio_pct}} of the previous 8-week average): they are rare ({{kpi_pcu_cut_share:pct2}} of weeks); {{pcu_phrase}} (median {{kpi_pcu_cut_median_ratio:x2}} of the previous 8-week level vs {{kpi_pcu_normal_median_ratio:x2}} normally), but the mean is {{kpi_pcu_cut_mean_ratio:x2}} because a few items jump a lot. This is an association, not a causal elasticity.

![Price cut uplift](outputs/charts/kpi_04_price_cut_uplift.png)

**Assumption-based safety stock** (formula `SS = z x sigma_weekly x sqrt(LT + R)`, `ROP = mean demand x LT + SS`; **assumed** LT = {{pol_lead_time_weeks}} week, R = {{pol_review_weeks}} week, z = {{pol_service_z:f2}} ~ 95%). On the real weekly variability this implies {{pol_ss_retail_value:usd}} of safety stock at retail value for {{pol_n_item_states:int}} item-state series ({{pol_ss_units:int}} units, median cover {{pol_ss_median_weeks_cover:f1}} weeks). A items hold {{pol_ss_value_A_share:pct0}} of it, C items {{pol_ss_value_C_share:pct0}}; erratic series are {{pol_erratic_item_share:pct0}} of series but {{pol_erratic_ss_share:pct0}} of the safety stock. Service targets by class (z = {{pol_z_A:f2}} / {{pol_z_B:f2}} / {{pol_z_C:f2}}) change the total by {{pol_ss_change_by_class:pct1}}.

![Assumed safety stock](outputs/charts/kpi_05_assumed_safety_stock.png)

*So what:* where to spend planning effort (A items, variable and erratic series) is measurable; the dollar amounts depend on the lead-time assumption and are only a structure for the discussion until real lead times exist.

### 4.4 Forecasting (`src/07_forecasting.py`, `notebooks/04_forecasting.ipynb`)

**Setup.** Weekly demand at **item x state** level ({{fc_n_series:int}} series, what a regional distribution centre would forecast; {{fc_n_series_dropped}} series with no sales in the train period are dropped). **Time-based split**: weeks 1-{{fc_train_weeks}} train ({{fc_train_rows:int}} rows, {{fc_train_start_date}} to {{fc_train_end_date}}), {{fc_dev_start_week}}-{{fc_dev_end_week}} dev ({{fc_dev_rows:int}}), {{fc_test_start_week}}-{{fc_test_end_week}} test ({{fc_test_rows:int}}, {{fc_test_start_date}} to {{fc_test_end_date}}); the test set is used once. {{dist_text}} Forecast horizon: next week (one step ahead); a row needs {{fc_min_history}} earlier on-sale weeks, so brand-new items are not forecast.
**Features** (known before the target week): lag 1/2/4/52, rolling mean 4/8, month (sin/cos), price ratio vs the previous 8 weeks, SNAP share of days, event flag. Each series is scaled by its train-period mean; features are standardised with train statistics only; model inputs and training targets are capped at the train {{fc_winsor_q:pct1}} percentile (evaluation never is).
**Models:** Naive, Moving average (window {{fc_ma_window}}), Exponential smoothing (alpha {{fc_ses_alpha}}) - window/alpha chosen on dev; seasonal naive as a reference; linear regression; and an MLP written from scratch in NumPy (He init, ReLU, L2, mini-batch Adam, early stopping, gradient-checked in `tests/test_nn_gradcheck.py`). Selected MLP on dev: hidden {{fc_mlp_hidden}}, L2 {{fc_mlp_l2}}, dropout {{fc_mlp_dropout}}.
**Metrics:** the single optimising metric is **WAPE** (sum of absolute errors / sum of actual demand); satisficing metrics are RMSE (must not be worse than naive on dev), bias within +/-{{fc_bias_limit:pct0}}, and interpretability. The decision rule was fixed in advance: a more complex model must beat the best baseline by at least {{fc_min_gain_pct}} on dev and be confirmed on test.

{{@table:forecast_model_comparison|model,WAPE_train,WAPE_dev,WAPE_test,RMSE_test,Bias_test,interpretable,passes_gates}}

![Model comparison](outputs/charts/forecast_01_model_comparison.png)

**Honest conclusion.** {{verdict_text}} {{seasonality_vs_lag}} The MLP {{gate_text}}. Over {{fc_n_seeds}} random seeds its test WAPE ranges {{fc_mlp_test_wape_min:pct1}} - {{fc_mlp_test_wape_max:pct1}}. As an independent check, scikit-learn's `MLPRegressor` with the same architecture gets {{fc_sklearn_check_test_wape:pct1}} on test, so the NumPy implementation is behaving. {{final_text}}

![Seed spread](outputs/charts/forecast_05_seed_spread.png)

**Where the MLP helps.** On test it beats the best baseline in {{fc_segments_mlp_better_test}} of {{fc_segments_total}} category / state / ABC segments, and in the {{fc_n_pricecut_rows_test:int}} price-cut rows its WAPE is {{fc_pricecut_wape_mlp_test:pct1}} vs {{fc_pricecut_wape_baseline_test:pct1}} - the known price is the one input the baselines ignore. Error is highest for C items (baseline {{fc_wape_test_abc_C_baseline:pct1}}) and lowest for A items ({{fc_wape_test_abc_A_baseline:pct1}}).

![Actual vs forecast](outputs/charts/forecast_03_actual_vs_forecast.png)

**Interpretability trade-off.** {{interp_text}}

![Interpretability](outputs/charts/forecast_06_interpretability.png)

**Bias / variance diagnosis** (best baseline's train error is the "human-level proxy"): avoidable bias of the MLP = {{fc_avoidable_bias_mlp:pct1}} (negative = it already beats the proxy on training weeks), variance = {{fc_variance_mlp:pct1}} (dev minus train error). {{fc_diagnosis_mlp}}

![Learning curve](outputs/charts/forecast_02_learning_curve.png)

**Error analysis** (the {{ea_top_n}} largest MLP errors on the dev set, which cover {{ea_top_share_of_dev_error:pct1}} of total dev error; full row-by-row table in `outputs/tables/error_analysis_top100.csv` with empty `manual_cause` / `notes` columns for you to fill in):

{{@table:error_analysis_tally}}

{{ea_text}} {{ea_top_category}} items are {{ea_top_category_n}} of the {{ea_top_n}}; A-class items account for {{ea_a_class_share:pct0}} of the big errors (they are the high-volume ones). The MLP beats the baseline on {{ea_mlp_beats_baseline_share:pct0}} of these rows. *So what:* {{ea_sowhat}}

![Error analysis](outputs/charts/forecast_04_error_analysis.png)

**What accuracy could be worth (simulation, assumption-based).** The data has no stock levels, so I replayed the real test-week demand through a weekly order-up-to policy with an **assumed** {{sim_lead_time_weeks}}-week lead time and review period (`src/policy_sim.py`). To reach {{sim_target_fill:pct0}} fill it needs {{sim_inv_at_target_mlp:usd}} of average inventory with the MLP forecast vs {{sim_inv_baseline:usd}} with {{fc_best_baseline}} ({{sim_text}}). This is relative, not absolute: the replay treats observed sales as true demand (it cannot see lost sales) and uses the assumed lead time. Use it to frame a pilot, not to claim savings.

![Policy simulation](outputs/charts/forecast_07_policy_simulation.png)

## 5. Repository structure

```
data/raw/        the 3 Kaggle M5 files (you download them; not in git)    data/processed/  cleaned panel, SQLite db (regenerated)
notebooks/       01 cleaning, 02 EDA, 03 KPIs, 04 forecasting, 05 recommendations
src/             numbered scripts 01..10 + library modules (panel, cleaning, kpis, features, baselines, nn_numpy ...)
sql/             schema + KPI, window-function, ABC, demand-variability, price/event, data-quality queries
outputs/         charts (PNG), tables (CSV), dashboard (CSV star schema + Excel), sql_results
tests/           pytest suite (tiny hand-made M5-style data)        docs/  data dictionary, data source, audit, templates
```

Setup and run order: **README_SETUP.md**. Interview preparation: **INTERVIEW_NOTES.md**.

## 6. Business recommendations (generated from the findings)

{{@file:outputs/recommendations.md}}

## 7. Limitations

- **No inventory, cost or lead-time data.** Fill rate, stock-outs, turnover, days of inventory and margin cannot be measured. Revenue is units x list price (no discounts at the till, no cost).
- **Sales are not demand.** If an item is out of stock the sale is lost and invisible; a zero-sales week is not necessarily zero demand (see the 4-week collapse and recovery of one top item in the actual-vs-forecast chart).
- **Assumption-based sections** (safety stock, policy simulation) depend on the assumed lead time and review period in `config.py`; treat the dollar values as structure, not findings.
- **One-step-ahead forecasts at item x state level.** Replenishment needs lead-time-ahead forecasts, and store-level series are more intermittent than the state level used here.
- **Single hold-out.** One 24-week test window (time-based, used once); dev and test are not identical (demand trends upward), so dev and test WAPE are not strictly comparable. Brand-new items (under {{fc_min_history}} weeks of history) are not forecast.
- **Associations, not causes.** SNAP, event and price-cut effects are observational; cuts may be timed with seasons and events.
- **Small neural network, modest data** ({{fc_train_rows:int}} training rows): results vary a little by seed (range shown above).
- **One retailer, 2011-2016, US.** Patterns may not transfer.

## 8. About the original ChainSight repo and the data change

This project restructures the original web-app repo in place: the React/FastAPI/Postgres/Docker layer, risk-scoring ML and anomaly-detection experiments were removed. It first ran on a *synthetic* supply-chain simulation; because synthetic data limits what a reviewer can trust, the whole analysis was re-run on the real M5 data (service-level KPIs that need stock data were dropped rather than invented). The audit and the migration notes are in `docs/AUDIT.md`.
