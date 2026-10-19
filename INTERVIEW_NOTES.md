# Interview notes - ChainSight Retail Demand & Inventory Analytics (real M5 / Walmart data)

(All numbers in this file are generated from the project outputs by `src/10_render_docs.py`. The data is real Kaggle M5 data - say so up front, and say just as clearly what it cannot measure: that honesty is the credibility.)

---

## 1. The 60-second pitch

"I analysed the real Kaggle M5 Walmart dataset - 3,049 items, 10 stores in 3 states, 273 weeks, $187.36M of revenue - end to end the way I would for a business team. I validated the data with a logged rule set; the real data was clean, but 21% of the history was pre-launch zeros that I masked instead of counting as demand. In SQL and pandas I showed that 41% of items make 80% of revenue, that FOODS sells up to 1.30x as much on SNAP days, and that revenue per on-sale series fell while the assortment grew, so growth looks assortment-driven rather than per-item. For forecasting I started with Naive, moving average and exponential smoothing, then added linear regression and a small neural network I wrote in NumPy as a challenger. The best baseline had 25.0% WAPE on the untouched test weeks, the MLP 24.5%, linear regression 26.1%. **Final model: Exp. smoothing.** Nothing more complex beat it by the required 5% on dev, so the simple baseline stays. The result is a prioritised, evidence-labelled action list - and an honest list of what M5 cannot tell you, such as fill rate, because it has no stock data."

## 2. The 3-minute walkthrough

| Time | What to say | Evidence in repo |
|---|---|---|
| 0:00 | Problem: which items and calendar effects drive a retailer's demand, and can we forecast it better than simple rules? | README section 1 |
| 0:25 | Data: real M5 (Kaggle). Cleaning is structural: checks, masking pre-launch zeros (21% of series-weeks), flags for 1,119 price jumps and 1,026 spikes. I verified revenue independently from the raw files. | `src/cleaning.py`, `outputs/tables/cleaning_log.csv`, `tests/test_cleaning.py` |
| 1:00 | EDA: assortment grew, so total growth overstates per-item growth; SNAP days, weekdays, events, department-level seasonality. So one flat parameter cannot work. | `outputs/charts/eda_*` |
| 1:30 | KPIs in SQL **and** pandas (a test checks they match): revenue, ABC (1,264 / 923 / 862 items), demand CV, intermittency, demand classes. | `sql/`, `src/kpis.py` |
| 2:00 | Safety stock - clearly labelled assumption-based (assumed 1-week lead time) because M5 has no lead times. | `kpi_05_assumed_safety_stock.png` |
| 2:20 | Forecasting with evaluation discipline: time split, one metric (WAPE), satisficing gates, baselines first, NN as challenger, bias/variance, error analysis. Honest result: The MLP is only marginally better than the best baseline (Exp. smoothing) on test: WAPE 24.5% vs 25.0% (2.3% relative, but its worst random seed does not beat the baseline) - below the 5% bar we set before looking at test. Linear regression with the same features is worse than the baseline (26.1% vs 25.0%): the extra features alone do not help, only the non-linear model gets a small gain. | `src/07_forecasting.py` |
| 2:50 | Recommendations with evidence labels; limitations (no stock data, one-step horizon, single hold-out). | README sections 6-7 |

## 3. Why / What / How

| Question | Answer |
|---|---|
| **Why real data, after starting synthetic?** | A reviewer cannot tell whether findings on synthetic data reflect the method or the generator. Real data forces honest handling of messy reality (pre-launch zeros, intermittent demand) - and it showed me which KPIs I could *not* compute. |
| **Why baselines first?** | They are free, explainable, and define what "good" means. A model that cannot beat a one-line rule is not worth deploying. They also act as the human-level proxy for diagnosing bias vs variance. |
| **Why a neural network at all?** | To test, honestly, whether non-linear interactions (price x event x lag) add value beyond simple rules - and to show I understand the mechanics (forward/back-prop, He init, Adam, L2, gradient checking). |
| **Why only as a challenger?** | It must earn its place: it had to beat the best baseline by >= 5%. Result (test): MLP vs baseline 2.3%, MLP vs linear regression 6.1%. |
| **What is the final answer?** | **Final model: Exp. smoothing.** Nothing more complex beat it by the required 5% on dev, so the simple baseline stays. |
| **How do I know it is not overfit?** | Time-based split, test used once, dev-train gap (variance) of -0.7%, 5 seeds (test WAPE 24.5% - 25.4%), early stopping, independent sklearn check (24.8%). |
| **How do I know the numbers are right?** | Pipeline revenue and units were recomputed independently from the raw files (long-format merge, no project code) and matched to the cent; SQL and pandas KPIs are tested to agree; the daily and weekly tables reconcile; every number in the docs is rendered from `key_numbers.json`. |

## 4. KPI definitions (know these cold)

| KPI | Formula | This project |
|---|---|---|
| Revenue | units x weekly sell price (no cost or discount data) | $187.36M |
| ABC | rank items by revenue; A = first 80% of cumulative revenue, B = next 15%, C = rest; class uses the share *before* the item | 1,264 / 923 / 862 items |
| Demand CV | std / mean of weekly units (stable < 0.5, variable < 1.0, erratic >= 1.0) | median 0.60 |
| Zero-sales week share | on-sale weeks with zero units / on-sale weeks (**not** a stock-out rate) | 24.1% |
| ADI / CV2 demand class | ADI = on-sale weeks / weeks with demand; CV2 = squared CV of non-zero weeks; smooth, erratic, intermittent, lumpy | 80% smooth |
| Safety stock (assumption-based) | z x sigma_weekly x sqrt(LT + R), assumed LT = 1 wk | $826K retail value |
| Reorder point | mean weekly demand x LT + safety stock | per item-state in `kpi_item_state_kpis.csv` |
| WAPE | sum abs(forecast - actual) / sum(actual) | best baseline 25.0% (test) |
| Bias | sum(forecast - actual) / sum(actual); + over-forecast, - under-forecast | MLP 0.7% (test) |
| **Not computable here** | fill rate, stock-out rate, turnover, days of inventory, lead-time reliability | M5 has no stock, cost or supplier data |

## 5. Expected interview questions and answers

### The dataset and the honest scope

**1. Why can't you report fill rate or inventory turnover?**
They need stock-on-hand, lost sales and cost. M5 has only sales, prices and a calendar, so a zero-sales week cannot be told apart from a stock-out. I would rather say "not measurable here, and this is the data I would ask for" than invent a number. The recommendation list ends with exactly that data request.

**2. What did cleaning involve on real data?**
Mostly validation: unique ids, a consistent hierarchy, a calendar that lines up with the sales columns, no negatives or missing values - the log proves each is zero. The real cleaning decisions were structural: drop the 2 trailing days that do not form a full week, and mask 21% of series-weeks with no price (item not yet on sale) so they are not counted as zero demand. Price jumps and demand spikes are flagged, never deleted.

**3. How did you check your own numbers?**
Recomputed units and revenue per store directly from the three raw files with a plain long-format merge and compared to the pipeline output (exact match), reconciled the daily and weekly tables, and wrote tests that compare the SQL result to pandas.

**4. Why item x state for forecasting, not item x store?**
Store-level series are far more intermittent; item x state (9,136 series) is what a regional distribution centre plans and gives a stabler signal. Limitation: store-level behaviour is hidden.

**5. Why did total revenue grow while revenue per on-sale series fell?**
Total weekly revenue grew 30% between 2012 and 2015, but the number of item-store series on sale grew 79%, so revenue per on-sale series fell 15%. Growth is consistent with a wider assortment rather than each item selling more (new items also tend to be smaller sellers, which on its own lowers the per-series average). It is a mix effect - looking only at the total would hide it. I would not claim a cause from this data alone.

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
Monthly average weekly rate divided by that year's average, per department, over complete years only (2012, 2013, 2014, 2015), normalised per on-sale item so a growing assortment is not mistaken for seasonality. 1.00 = a normal month.

**16. Is the SNAP effect causal?**
No. SNAP days fall early in the month, so part of the lift is the normal start-of-month pattern. I report it as an association and recommend planning around it, not attributing it.

**17. ABC says 41% of items are A. Isn't that unusual?**
Classic ABC finds a small A group; here the catalogue is long and flat, so 80% of revenue needs 41% of items (the top 100 are only 23%). That is a finding, and why I recommend splitting A by variability.

**18. What is demand CV / ADI used for?**
CV is unit-free variability (std/mean), ADI measures intermittency; together (Syntetos-Boylan) they say which series suit simple methods (80% are smooth) and which need special handling.

**19. Explain safety stock and why it is labelled assumption-based.**
Safety stock protects against demand variation over the lead time plus review period: `z x sigma x sqrt(LT + R)`. M5 has no lead times, so LT = 1 week is an assumption in `config.py`; the real part is the demand variability.

### Forecasting

**20. Why WAPE, not MAPE?**
MAPE divides by each actual: undefined at zero and dominated by tiny items - fatal with 24% zero weeks. WAPE divides total error by total demand: volume-weighted, never undefined.

**21. Why a time-based split? Why must dev and test match?**
A random split lets the model see the future. Dev and test are consecutive recent blocks so they come from the same distribution. Caveat: demand trends up, so they are close but not identical. Dev and test are consecutive recent blocks, but not identical: mean relative demand is 1.10 on dev vs 1.18 on test (demand trends upward); price-cut weeks are 0.4% of dev rows vs 0.3% of test rows.

**22. What is optimising vs satisficing here?**
Optimise WAPE (one number to rank models). Satisficing gates only need to be met: |bias| <= 5% and RMSE no worse than naive. A model that wins on WAPE but is biased low would cause stock-outs.

**23. Does the neural network beat the baseline?**
The MLP is only marginally better than the best baseline (Exp. smoothing) on test: WAPE 24.5% vs 25.0% (2.3% relative, but its worst random seed does not beat the baseline) - below the 5% bar we set before looking at test. Linear regression with the same features is worse than the baseline (26.1% vs 25.0%): the extra features alone do not help, only the non-linear model gets a small gain. **Final model: Exp. smoothing.** Nothing more complex beat it by the required 5% on dev, so the simple baseline stays. The honest message: complexity has to be paid for with accuracy *and* interpretability, and a pre-registered bar (5%) keeps me from rationalising a small gain.

**24. Why did seasonal naive do so badly?**
The seasonal-naive reference (same week last year) scores 46.4% on test, far worse than the simple baselines: here recent weeks carry much more information than the same week a year ago (the 52-week lag ranks 8 of 11 in the MLP's permutation importance).

**25. How did you do error analysis?**
Took the 100 largest dev errors, tagged each (outlier week, price-cut week, post-cut week, seasonal turn, event week), assigned a primary cause by priority, and tallied. The largest bucket is 'outlier week' with 79 of the top 100 errors (79%). But that tag is true for 29% of ALL dev rows, so among the big errors it is only 2.7x as common as normal; price-cut weeks are 10.0x over-represented (but only 4 rows). 46% of the big errors are under-forecasts. I report the base rate and lift because a tag that is true for most rows explains little. I left a `manual_cause` column for manual review.

**26. How do you diagnose bias vs variance with a baseline as proxy?**
Avoidable bias = train error minus proxy error; variance = dev error minus train error. Here avoidable bias = -1.4% and variance = -0.7%. The model already beats the baseline proxy on the training weeks and generalises: bias and variance are both small. Remaining error is likely noise or information these features do not contain.

**27. The simulation says the MLP needs less inventory - why don't you switch to it?**
The simulation is assumption-based (assumed lead time, sales treated as demand), and its gap is bigger than the WAPE gap because safety stock follows the spread of errors, not their average size. It justifies a pilot with real stock data, not a model switch.

### Neural-network basics

**28. Explain forward and back propagation in your MLP.**
Forward: `Z = A_prev W + b`, ReLU on hidden layers, linear output. Loss: mean of 0.5 x squared error + (lambda/2) x sum of squared weights. Backward: output gradient `(y_hat - y)/m`, then per layer `dW = A_prev^T dZ + lambda W`, `dA_prev = dZ W^T`, times the ReLU derivative. All in `src/nn_numpy.py`.

**29. Why ReLU and He initialisation?**
ReLU avoids vanishing gradients and is cheap. He initialisation draws weights with variance 2/n_in, keeping the signal scale stable through ReLU layers.

**30. How do you fight overfitting?**
L2, optional dropout, early stopping on dev (best epoch 6), a small network (337 weights), and the train/dev learning curves.

**31. What is gradient checking and why did my first attempt fail?**
Compare backprop gradients with `(L(w+e) - L(w-e)) / 2e`; the relative difference should be tiny. With all-zero biases a ReLU unit can sit exactly at 0 where the derivative is undefined, so the check disagreed; non-zero biases fixed it (see `tests/test_nn_gradcheck.py`).

**32. Mini-batch and Adam?**
Mini-batches give noisy but cheap gradients and faster progress than full-batch; Adam keeps running averages of the gradient (momentum) and its square (per-weight step size) with bias correction.

**33. Why normalise inputs with train statistics?**
Features on very different scales slow and destabilise training; dev/test statistics would leak the future.

## 6. Resume bullets (what / how / why)

- **What:** Analysed 3,049 items x 10 stores x 273 weeks of real Walmart M5 data ($187.36M revenue). **How:** validated and cleaned the data (Python, pandas, NumPy), built a SQLite star schema with window-function KPIs (ABC, demand variability, SNAP / event effects) cross-checked against pandas. **Why:** showed that 41% of items drive 80% of revenue and that revenue growth is consistent with a wider assortment rather than per-item growth.
- **What:** Benchmarked Naive / moving-average / exponential-smoothing baselines against linear regression and a from-scratch NumPy MLP on a time-based split (WAPE 25.0% baseline vs 24.5% MLP). **How:** one optimising metric, satisficing gates, bias/variance diagnosis, error analysis of the 100 largest errors, 5-seed spread, gradient-checked backprop. **Why:** a pre-set 5% bar kept the simple model when the network's gain was small (2.3%).
- **What:** Delivered a reproducible pipeline (10 scripts, 5 notebooks, pytest suite), Excel / Power BI-ready outputs and evidence-labelled recommendations. **How:** every figure in the README is generated from the data; assumption-based results are labelled as such. **Why:** credible, auditable analysis a business team can act on.

## 7. Limitations and next steps

- Get stock-on-hand, stock-out flags, cost and supplier lead times: then fill rate, turnover and a real reorder policy become measurable.
- Multi-step (lead-time-ahead) and probabilistic forecasts feeding safety stock directly.
- Store-level and hierarchical forecasts (reconcile item, state and total), and a cold-start approach for new items.
- Controlled price tests before trusting any price-cut uplift.
- Rolling-origin evaluation (several test windows) instead of a single hold-out.
- Power BI dashboard on `outputs/dashboard/` (star-schema CSVs are ready).
