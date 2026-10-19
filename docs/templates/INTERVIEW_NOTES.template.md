# Interview notes - ChainSight Retail Demand & Inventory Analytics (real M5 / Walmart data)

(All numbers in this file are generated from the project outputs by `src/10_render_docs.py`. The data is real Kaggle M5 data - say so up front, and say just as clearly what it cannot measure: that honesty is the credibility.)

---

## 1. The 60-second pitch

"I analysed the real Kaggle M5 Walmart dataset - {{data_n_items:int}} items, {{data_n_stores}} stores in {{data_n_states}} states, {{data_n_weeks}} weeks, {{data_total_revenue:usd}} of revenue - end to end the way I would for a business team. I validated the data with a logged rule set; the real data was clean, but {{dq_not_on_sale_share:pct0}} of the history was pre-launch zeros that I masked instead of counting as demand. In SQL and pandas I showed that {{kpi_abc_A_items_share:pct0}} of items make {{kpi_abc_A_revenue_share:pct0}} of revenue, that FOODS sells up to {{eda_snap_foods_max_ratio:x2}} as much on SNAP days, and that revenue per on-sale series fell while the assortment grew, so growth looks assortment-driven rather than per-item. For forecasting I started with Naive, moving average and exponential smoothing, then added linear regression and a small neural network I wrote in NumPy as a challenger. The best baseline had {{bl_wape_test:pct1}} WAPE on the untouched test weeks, the MLP {{fc_wape_test_mlp:pct1}}, linear regression {{fc_wape_test_linear:pct1}}. {{final_text}} The result is a prioritised, evidence-labelled action list - and an honest list of what M5 cannot tell you, such as fill rate, because it has no stock data."

## 2. The 3-minute walkthrough

| Time | What to say | Evidence in repo |
|---|---|---|
| 0:00 | Problem: which items and calendar effects drive a retailer's demand, and can we forecast it better than simple rules? | README section 1 |
| 0:25 | Data: real M5 (Kaggle). Cleaning is structural: checks, masking pre-launch zeros ({{dq_not_on_sale_share:pct0}} of series-weeks), flags for {{dq_price_jumps:int}} price jumps and {{dq_spike_weeks:int}} spikes. I verified revenue independently from the raw files. | `src/cleaning.py`, `outputs/tables/cleaning_log.csv`, `tests/test_cleaning.py` |
| 1:00 | EDA: assortment grew, so total growth overstates per-item growth; SNAP days, weekdays, events, department-level seasonality. So one flat parameter cannot work. | `outputs/charts/eda_*` |
| 1:30 | KPIs in SQL **and** pandas (a test checks they match): revenue, ABC ({{kpi_abc_A_n:int}} / {{kpi_abc_B_n:int}} / {{kpi_abc_C_n:int}} items), demand CV, intermittency, demand classes. | `sql/`, `src/kpis.py` |
| 2:00 | Safety stock - clearly labelled assumption-based (assumed {{pol_lead_time_weeks}}-week lead time) because M5 has no lead times. | `kpi_05_assumed_safety_stock.png` |
| 2:20 | Forecasting with evaluation discipline: time split, one metric (WAPE), satisficing gates, baselines first, NN as challenger, bias/variance, error analysis. Honest result: {{verdict_text}} | `src/07_forecasting.py` |
| 2:50 | Recommendations with evidence labels; limitations (no stock data, one-step horizon, single hold-out). | README sections 6-7 |

## 3. Why / What / How

| Question | Answer |
|---|---|
| **Why real data, after starting synthetic?** | A reviewer cannot tell whether findings on synthetic data reflect the method or the generator. Real data forces honest handling of messy reality (pre-launch zeros, intermittent demand) - and it showed me which KPIs I could *not* compute. |
| **Why baselines first?** | They are free, explainable, and define what "good" means. A model that cannot beat a one-line rule is not worth deploying. They also act as the human-level proxy for diagnosing bias vs variance. |
| **Why a neural network at all?** | To test, honestly, whether non-linear interactions (price x event x lag) add value beyond simple rules - and to show I understand the mechanics (forward/back-prop, He init, Adam, L2, gradient checking). |
| **Why only as a challenger?** | It must earn its place: it had to beat the best baseline by >= {{fc_min_gain_pct}}. Result (test): MLP vs baseline {{fc_mlp_rel_gain_vs_baseline_test:pct1}}, MLP vs linear regression {{fc_mlp_rel_gain_vs_linear_test:pct1}}. |
| **What is the final answer?** | {{final_text}} |
| **How do I know it is not overfit?** | Time-based split, test used once, dev-train gap (variance) of {{fc_variance_mlp:pct1}}, {{fc_n_seeds}} seeds (test WAPE {{fc_mlp_test_wape_min:pct1}} - {{fc_mlp_test_wape_max:pct1}}), early stopping, independent sklearn check ({{fc_sklearn_check_test_wape:pct1}}). |
| **How do I know the numbers are right?** | Pipeline revenue and units were recomputed independently from the raw files (long-format merge, no project code) and matched to the cent; SQL and pandas KPIs are tested to agree; the daily and weekly tables reconcile; every number in the docs is rendered from `key_numbers.json`. |

## 4. KPI definitions (know these cold)

| KPI | Formula | This project |
|---|---|---|
| Revenue | units x weekly sell price (no cost or discount data) | {{kpi_total_revenue:usd}} |
| ABC | rank items by revenue; A = first {{abc_a_cut_pct}} of cumulative revenue, B = next {{abc_b_cut_pct}}, C = rest; class uses the share *before* the item | {{kpi_abc_A_n:int}} / {{kpi_abc_B_n:int}} / {{kpi_abc_C_n:int}} items |
| Demand CV | std / mean of weekly units (stable < 0.5, variable < 1.0, erratic >= 1.0) | median {{eda_cv_median:f2}} |
| Zero-sales week share | on-sale weeks with zero units / on-sale weeks (**not** a stock-out rate) | {{eda_zero_week_pct:pct1}} |
| ADI / CV2 demand class | ADI = on-sale weeks / weeks with demand; CV2 = squared CV of non-zero weeks; smooth, erratic, intermittent, lumpy | {{kpi_class_smooth_item_share:pct0}} smooth |
| Safety stock (assumption-based) | z x sigma_weekly x sqrt(LT + R), assumed LT = {{pol_lead_time_weeks}} wk | {{pol_ss_retail_value:usd}} retail value |
| Reorder point | mean weekly demand x LT + safety stock | per item-state in `kpi_item_state_kpis.csv` |
| WAPE | sum abs(forecast - actual) / sum(actual) | best baseline {{bl_wape_test:pct1}} (test) |
| Bias | sum(forecast - actual) / sum(actual); + over-forecast, - under-forecast | MLP {{fc_bias_test_mlp:pct1}} (test) |
| **Not computable here** | fill rate, stock-out rate, turnover, days of inventory, lead-time reliability | M5 has no stock, cost or supplier data |

## 5. Expected interview questions and answers

### The dataset and the honest scope

**1. Why can't you report fill rate or inventory turnover?**
They need stock-on-hand, lost sales and cost. M5 has only sales, prices and a calendar, so a zero-sales week cannot be told apart from a stock-out. I would rather say "not measurable here, and this is the data I would ask for" than invent a number. The recommendation list ends with exactly that data request.

**2. What did cleaning involve on real data?**
Mostly validation: unique ids, a consistent hierarchy, a calendar that lines up with the sales columns, no negatives or missing values - the log proves each is zero. The real cleaning decisions were structural: drop the {{dq_dropped_days}} trailing days that do not form a full week, and mask {{dq_not_on_sale_share:pct0}} of series-weeks with no price (item not yet on sale) so they are not counted as zero demand. Price jumps and demand spikes are flagged, never deleted.

**3. How did you check your own numbers?**
Recomputed units and revenue per store directly from the three raw files with a plain long-format merge and compared to the pipeline output (exact match), reconciled the daily and weekly tables, and wrote tests that compare the SQL result to pandas.

**4. Why item x state for forecasting, not item x store?**
Store-level series are far more intermittent; item x state ({{fc_n_series:int}} series) is what a regional distribution centre plans and gives a stabler signal. Limitation: store-level behaviour is hidden.

**5. Why did total revenue grow while revenue per on-sale series fell?**
{{growth_phrase}} It is a mix effect - looking only at the total would hide it. I would not claim a cause from this data alone.

### SQL

**6. INNER JOIN vs LEFT JOIN - where did you use each?**
INNER keeps matching rows (fact rows to item/store/week dimensions). LEFT keeps all left rows; I use it in the orphan checks (`fact LEFT JOIN dim ... WHERE dim.key IS NULL`). All integrity checks in `sql/06_data_quality_checks.sql` return 0.

**7. Window function vs GROUP BY?**
GROUP BY collapses rows; a window function keeps every row and adds a calculation over a frame. I used `LAG` for week-over-week growth, `AVG(...) OVER (ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)` for moving averages, `LAG(x, 12)` for year-over-year, `ROW_NUMBER() OVER (PARTITION BY department ...)` for the top 3 items, `RANK` for stores within a state, and a running total per category-year (`sql/02_window_functions.sql`).

**8. Walk me through the ABC query.**
Revenue per item in a CTE; then `SUM(revenue) OVER (ORDER BY revenue DESC, item_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` is the cumulative revenue. I classify with the share *before* the item (cumulative minus own revenue), so the item that crosses the 80% line is still an A. `ROWS` (not the default `RANGE`) and the `item_id` tie-break keep ties deterministic. A test proves SQL and pandas classes are identical.

**9. How did you find long streaks of zero sales?**
"Gaps and islands": for zero-sales weeks, `week_idx - ROW_NUMBER()` over the item's zero weeks is constant inside an unbroken streak; group by it and count.

**10. How did you compare an event day with normal days in SQL?**
`LAG`/`LEAD` partitioned by weekday give the same weekday one week before and after; I keep only events whose neighbours are event-free and divide the event day by their average. That controls for weekday pattern and season.

**11. SQLite has no STDDEV. What did you do?**
Computed the population standard deviation as `sqrt(E[x^2] - E[x]^2)` from `AVG(units*units)` and `AVG(units)`, and tested it against pandas.

### Pandas / NumPy

**12. Why NumPy matrices instead of a long DataFrame?**
30,490 series x 273 weeks is 8.3 million numbers - tiny as a matrix, slow as row-by-row pandas. Lags, rolling means and baselines become vectorised column operations; NaN means "not on sale".

**13. How did you prevent leakage in lag/rolling features?**
Lags and rolling means only use weeks before the target week; scaling factors, standardisation and the outlier cap come from the train period only. Tests check that changing dev/test values does not move the train-based scales and that baselines never read the target week.

**14. How do you handle missing values?**
By meaning: no price = not on sale (masked, not zero demand). There were no missing sales values; the log records that count as 0.

### EDA and KPIs

**15. How did you measure seasonality?**
Monthly average weekly rate divided by that year's average, per department, over complete years only ({{eda_seasonality_years}}), normalised per on-sale item so a growing assortment is not mistaken for seasonality. 1.00 = a normal month.

**16. Is the SNAP effect causal?**
No. SNAP days fall early in the month, so part of the lift is the normal start-of-month pattern. I report it as an association and recommend planning around it, not attributing it.

**17. ABC says {{kpi_abc_A_items_share:pct0}} of items are A. Isn't that unusual?**
Classic ABC finds a small A group; here the catalogue is long and flat, so 80% of revenue needs {{kpi_abc_A_items_share:pct0}} of items (the top 100 are only {{kpi_top100_items_revenue_share:pct0}}). That is a finding, and why I recommend splitting A by variability.

**18. What is demand CV / ADI used for?**
CV is unit-free variability (std/mean), ADI measures intermittency; together (Syntetos-Boylan) they say which series suit simple methods ({{kpi_class_smooth_item_share:pct0}} are smooth) and which need special handling.

**19. Explain safety stock and why it is labelled assumption-based.**
Safety stock protects against demand variation over the lead time plus review period: `z x sigma x sqrt(LT + R)`. M5 has no lead times, so LT = {{pol_lead_time_weeks}} week is an assumption in `config.py`; the real part is the demand variability.

### Forecasting

**20. Why WAPE, not MAPE?**
MAPE divides by each actual: undefined at zero and dominated by tiny items - fatal with {{eda_zero_week_pct:pct0}} zero weeks. WAPE divides total error by total demand: volume-weighted, never undefined.

**21. Why a time-based split? Why must dev and test match?**
A random split lets the model see the future. Dev and test are consecutive recent blocks so they come from the same distribution. Caveat: demand trends up, so they are close but not identical. {{dist_text}}

**22. What is optimising vs satisficing here?**
Optimise WAPE (one number to rank models). Satisficing gates only need to be met: |bias| <= {{fc_bias_limit:pct0}} and RMSE no worse than naive. A model that wins on WAPE but is biased low would cause stock-outs.

**23. Does the neural network beat the baseline?**
{{verdict_text}} {{final_text}} The honest message: complexity has to be paid for with accuracy *and* interpretability, and a pre-registered bar ({{fc_min_gain_pct}}) keeps me from rationalising a small gain.

**24. Why did seasonal naive do so badly?**
{{seasonality_vs_lag}}

**25. How did you do error analysis?**
Took the {{ea_top_n}} largest dev errors, tagged each (outlier week, price-cut week, post-cut week, seasonal turn, event week), assigned a primary cause by priority, and tallied. {{ea_text}} I report the base rate and lift because a tag that is true for most rows explains little. I left a `manual_cause` column for manual review.

**26. How do you diagnose bias vs variance with a baseline as proxy?**
Avoidable bias = train error minus proxy error; variance = dev error minus train error. Here avoidable bias = {{fc_avoidable_bias_mlp:pct1}} and variance = {{fc_variance_mlp:pct1}}. {{fc_diagnosis_mlp}}

**27. The simulation says the MLP needs less inventory - why don't you switch to it?**
The simulation is assumption-based (assumed lead time, sales treated as demand), and its gap is bigger than the WAPE gap because safety stock follows the spread of errors, not their average size. It justifies a pilot with real stock data, not a model switch.

### Neural-network basics

**28. Explain forward and back propagation in your MLP.**
Forward: `Z = A_prev W + b`, ReLU on hidden layers, linear output. Loss: mean of 0.5 x squared error + (lambda/2) x sum of squared weights. Backward: output gradient `(y_hat - y)/m`, then per layer `dW = A_prev^T dZ + lambda W`, `dA_prev = dZ W^T`, times the ReLU derivative. All in `src/nn_numpy.py`.

**29. Why ReLU and He initialisation?**
ReLU avoids vanishing gradients and is cheap. He initialisation draws weights with variance 2/n_in, keeping the signal scale stable through ReLU layers.

**30. How do you fight overfitting?**
L2, optional dropout, early stopping on dev (best epoch {{fc_mlp_best_epoch}}), a small network ({{fc_n_parameters:int}} weights), and the train/dev learning curves.

**31. What is gradient checking and why did my first attempt fail?**
Compare backprop gradients with `(L(w+e) - L(w-e)) / 2e`; the relative difference should be tiny. With all-zero biases a ReLU unit can sit exactly at 0 where the derivative is undefined, so the check disagreed; non-zero biases fixed it (see `tests/test_nn_gradcheck.py`).

**32. Mini-batch and Adam?**
Mini-batches give noisy but cheap gradients and faster progress than full-batch; Adam keeps running averages of the gradient (momentum) and its square (per-weight step size) with bias correction.

**33. Why normalise inputs with train statistics?**
Features on very different scales slow and destabilise training; dev/test statistics would leak the future.

## 6. Resume bullets (what / how / why)

- **What:** Analysed {{data_n_items:int}} items x {{data_n_stores}} stores x {{data_n_weeks}} weeks of real Walmart M5 data ({{data_total_revenue:usd}} revenue). **How:** validated and cleaned the data (Python, pandas, NumPy), built a SQLite star schema with window-function KPIs (ABC, demand variability, SNAP / event effects) cross-checked against pandas. **Why:** showed that {{kpi_abc_A_items_share:pct0}} of items drive {{kpi_abc_A_revenue_share:pct0}} of revenue and that revenue growth is consistent with a wider assortment rather than per-item growth.
- **What:** Benchmarked Naive / moving-average / exponential-smoothing baselines against linear regression and a from-scratch NumPy MLP on a time-based split (WAPE {{bl_wape_test:pct1}} baseline vs {{fc_wape_test_mlp:pct1}} MLP). **How:** one optimising metric, satisficing gates, bias/variance diagnosis, error analysis of the 100 largest errors, 5-seed spread, gradient-checked backprop. **Why:** a pre-set {{fc_min_gain_pct}} bar kept the simple model when the network's gain was small ({{fc_mlp_rel_gain_vs_baseline_test:pct1}}).
- **What:** Delivered a reproducible pipeline (10 scripts, 5 notebooks, pytest suite), Excel / Power BI-ready outputs and evidence-labelled recommendations. **How:** every figure in the README is generated from the data; assumption-based results are labelled as such. **Why:** credible, auditable analysis a business team can act on.

## 7. Limitations and next steps

- Get stock-on-hand, stock-out flags, cost and supplier lead times: then fill rate, turnover and a real reorder policy become measurable.
- Multi-step (lead-time-ahead) and probabilistic forecasts feeding safety stock directly.
- Store-level and hierarchical forecasts (reconcile item, state and total), and a cold-start approach for new items.
- Controlled price tests before trusting any price-cut uplift.
- Rolling-origin evaluation (several test windows) instead of a single hold-out.
- Power BI dashboard on `outputs/dashboard/` (star-schema CSVs are ready).
