# Interview notes - ChainSight Inventory & Demand Analytics

(All numbers in this file are generated from the project outputs by `src/10_render_docs.py`. Data is synthetic - say so up front; it is a strength, because you can explain exactly how it was built.)

---

## 1. The 60-second pitch

"I took a supply-chain dataset - 90 SKUs, 5 warehouses, 104 weeks of history - and worked it end to end like I would for a business team. I cleaned 5,998 bad records with a logged, tested rule set, built SQL and pandas KPIs, and found that fill rate was 85.6% and had fell from 92.9% to 78.7%, costing $10.76M in lost revenue. The root cause was a reorder policy with a single set date (2024-03-31) that is not refreshed as demand grows: 91% of SKU-warehouses were under-protected and stocked out on 19.7% of days versus 2.1% for the rest. On forecasting I started with Naive, moving average and exponential smoothing, then added linear regression and a small neural network I wrote in NumPy as a challenger. The best baseline had 11.4% WAPE on the untouched test weeks, the MLP 10.1%, linear regression 10.2%. **Final model: Linear regression.** It earned its place on the dev set and was confirmed on test. The result is a prioritised action list: fix the top-15 SKUs, refresh reorder points quarterly, set service targets by ABC class, and manage supplier reliability."

## 2. The 3-minute walkthrough

| Time | What to say | Evidence in repo |
|---|---|---|
| 0:00 | Problem: the business keeps running out of its most valuable items; I was asked where, why and what to do. | README section 1 |
| 0:30 | Data: 7 tables, synthetic but messy (duplicates, mixed dates, impossible values). Cleaning is rule-by-rule with a log; I proved it works by checking the cleaned data against the hidden clean truth. | `src/cleaning.py`, `outputs/tables/cleaning_log.csv`, `tests/test_cleaning.py` |
| 1:00 | EDA: trend 14% per year, category-specific seasonality, promo weeks at 1.23x normal. So one flat policy cannot work. | `outputs/charts/eda_*` |
| 1:30 | KPIs in SQL **and** pandas (a test checks they match): fill rate, stockout rate, turnover 24.6x, days of inventory 14.5, ABC, CV, lead time. Key insight: fill rate by ABC class is nearly identical across A, B and C items (the policy ignores how important an item is). | `sql/`, `src/kpis.py` |
| 2:00 | Reorder point / safety stock check using actual lead times and variability: bigger policy gap -> more stockouts (correlation 0.79). | `kpi_09_policy_gap_vs_stockouts.png` |
| 2:20 | Forecasting with evaluation discipline: time split, one metric (WAPE), satisficing gates, baselines first, NN as challenger, bias/variance, error analysis. Honest result: The MLP beats the best baseline (Exp. smoothing) on the untouched test weeks: WAPE 10.1% vs 11.4% (11.1% relative improvement, and even its worst random seed beats the baseline). But plain linear regression with the same features already gets 10.2% (10.0% better than the baseline); the hidden layers add only 1.3% on top of that - below the bar, so the extra complexity is not justified. | `src/07_forecasting.py` |
| 2:50 | Recommendations with a value at stake each; limitations (synthetic, 1-step horizon). | README sections 6-7 |

## 3. Why / What / How

| Question | Answer |
|---|---|
| **Why baselines first?** | They are free, explainable, and define what "good" means. A model that cannot beat a one-line rule is not worth deploying. They also act as a human-level proxy for diagnosing bias vs variance. |
| **Why a neural network at all?** | To test, honestly, whether non-linear interactions (e.g. promo x season) add value beyond simple rules - and to show I understand the mechanics (forward/back-prop, He init, Adam, L2, gradient checking). |
| **Why only as a challenger?** | It must earn its place: here it needed to beat the best baseline by >= 5% to justify the complexity. Result (test): MLP vs baseline 11.1%, MLP vs linear regression 1.3%. |
| **What is the final answer?** | **Final model: Linear regression.** It earned its place on the dev set and was confirmed on test. |
| **How do I know it is not overfit?** | Time-based split, test used once, dev-train gap (variance) of 0.7%, 5 seeds (test WAPE 10.1% - 10.6%), early stopping, independent sklearn check (10.5%). |
| **How would this help the business?** | Forecast + promo calendar -> earlier reorders; error-based safety stock is indicatively lower by 14.8% vs the baseline. |

## 4. KPI definitions (know these cold)

| KPI | Formula | This project |
|---|---|---|
| Fill rate | units fulfilled / units demanded | 85.6% |
| Stockout rate | share of SKU-warehouse-days where demand was not fully met | 13.0% |
| Inventory turnover | annualised COGS / average inventory value (COGS = fulfilled units x unit cost) | 24.6x |
| Days of inventory | average units on hand / average daily units sold (~ 365 / turnover) | 14.5 |
| Reorder point | mean daily demand x mean lead time + safety stock | per SKU-warehouse in `kpi_policy_check.csv` |
| Safety stock | z x sqrt((LT + R) x sigma_d^2 + mean_d^2 x sigma_LT^2); z = 1.65 for ~95% | median recommended / current = 3.6x |
| Demand CV | std / mean of daily demand (Low < 0.30, Medium < 0.50, High >= 0.50) | median 0.38 |
| ABC | rank by revenue; A = first 80% of cumulative revenue, B = next 15%, C = last 5% | 25 / 26 / 39 SKUs |
| Lead time | actual delivery date - order date; delay = actual - promised; on-time = delay <= 0 | 17.2 days, 53.1% on time |
| WAPE | sum abs(forecast - actual) / sum(actual) | best baseline 11.4% (test) |
| Bias | sum(forecast - actual) / sum(actual); + over-forecast, - under-forecast | MLP -0.7% (test) |

## 5. Expected interview questions and answers

### SQL

**1. INNER JOIN vs LEFT JOIN - where did you use each?**
INNER keeps only matching rows (demand rows joined to products for prices). LEFT keeps all rows from the left table; I used it for orphan checks (`demand_daily LEFT JOIN products ... WHERE p.sku IS NULL` finds demand rows with no product). See `sql/06_data_quality_checks.sql`; all orphan counts are 0.

**2. Window function vs GROUP BY?**
GROUP BY collapses rows to one per group; a window function keeps every row and adds a calculation over a frame. I used `LAG` for week-over-week growth, `AVG(...) OVER (ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)` for a 4-week moving average, `ROW_NUMBER() OVER (PARTITION BY category ...)` for top-3 SKUs per category, and a running total of stockout days (`sql/02_window_functions.sql`).

**3. Walk me through the ABC query.**
Revenue per SKU in a CTE; then `SUM(revenue) OVER (ORDER BY revenue DESC, sku ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` gives the cumulative revenue. I classify using the share *before* the item (cumulative - own revenue) so the item that crosses 80% is still an A. I specify `ROWS` (not the default `RANGE`) and add `sku` as a tie-break so equal revenues do not behave unpredictably. A test proves the SQL classes equal the pandas classes.

**4. How did you find consecutive stockout days?**
"Gaps and islands": for stockout rows, `ROW_NUMBER()` over all days minus `ROW_NUMBER()` over stockout days is constant inside an unbroken streak; group by it and count (`longest_stockout_streaks`).

**5. How do you avoid double counting when joining demand and inventory?**
Watch the grain. Demand is SKU x warehouse x day; joining straight to purchase orders would multiply rows. I aggregate each table to the grain I need first (e.g. inventory value per day), then join. Average inventory = average of the daily *total*, not the average of per-row values - dividing total COGS by a per-row average inflates turnover by roughly the number of SKU-warehouses (a bug I found in the original repo, see `docs/AUDIT.md`).

### Pandas

**6. `groupby().transform` vs `apply`?**
`transform` returns a result aligned to the original rows (same length), so I can attach the SKU-warehouse median to every demand row to detect extra-zero typos; `agg`/`apply` return one row per group.

**7. How did you prevent leakage in rolling/lag features?**
`shift(1)` before `rolling(...)` so the window ends at the *previous* week; scaling factors and standardisation use train-period statistics only. A test changes dev/test values and asserts the train-based scales do not move (`tests/test_forecasting_pieces.py`).

**8. How do you handle missing values?**
Depends on meaning. Stock on hand is a level, so forward-fill the last known value. Missing demand is filled with units fulfilled (a lower bound of true demand, logged). Unit cost comes from the SKU's average PO cost, falling back to the category median. Every imputation is counted in `cleaning_log.csv`.

**9. Common `merge` pitfalls?**
Many-to-many fan-out, whitespace/case differences in keys (so I standardise codes first), and silent row loss with inner joins; I check row counts and run an orphan check.

### EDA

**10. What did you look at first?**
Row counts, duplicates on the business key, nulls, ranges (negatives, fulfilled > demanded), date formats - then trend, seasonality, category/region/SKU cuts and the promo effect.

**11. How did you measure seasonality?**
Monthly demand divided by that year's average month, per category, averaged over the years -> an index where 1.00 is a normal month. Trend is only partly removed, which is fine for exploration (and a stated limitation).

**12. Promo spike vs data error?**
A promo spike is explained by the promo calendar and is modest (1.23x on average); a typo is more than 20x the SKU-warehouse median. I replaced only the second kind, with a documented threshold.

### KPIs

**13. Fill rate vs stockout rate vs service level?**
Fill rate is volume based (units delivered / demanded). Stockout rate counts occasions (days with unmet demand). Cycle service level is the probability of no stockout in a replenishment cycle - what `z` in the safety-stock formula targets. They can disagree: many small shortages hurt stockout rate more than fill rate.

**14. Explain safety stock and the reorder point.**
Reorder point = expected demand during lead time + safety stock. Safety stock protects against variation in demand *and* lead time, over lead time plus the review period: `z x sqrt((LT+R) sigma_d^2 + mean_d^2 sigma_LT^2)`. The existing policy ignored lead-time variability and was never refreshed.

**15. What is demand CV used for?**
It is unit-free variability (std/mean), so SKUs of different sizes are comparable. High CV needs more safety stock per unit of demand and is harder to forecast; combined with ABC it gives an ABC x variability matrix (20 of 25 A items are medium or high variability).

**16. Limitations of ABC?**
It uses revenue only (not margin or criticality), is a snapshot, and says nothing about variability - which is why I add CV bands.

### Forecasting

**17. Why WAPE, not MAPE?**
MAPE divides by each actual - undefined at zero and dominated by tiny SKUs. WAPE divides total error by total demand: volume-weighted, never undefined, and reads "we are off by x% of demand".

**18. Why a time-based split? Why must dev and test match?**
A random split lets the model see the future. Dev and test are consecutive recent blocks so they come from the same distribution; otherwise improvements on dev would not transfer to test. Honest caveat: demand trends up, so they are close but not identical. Dev and test are consecutive recent blocks of the same process, but not identical: mean relative demand is 1.08 on dev vs 1.18 on test (demand trends upward), promo-week share 12.0% vs 10.9%.

**19. What is optimising vs satisficing here?**
Optimise WAPE (one number to rank models). Satisficing gates must simply be met: |bias| <= 5% and RMSE no worse than naive. A model that wins on WAPE but is biased low would cause stockouts.

**20. How did you do error analysis?**
Took the 100 largest dev errors, tagged each (promo week, post-promo week, outlier week, seasonal turn), assigned a primary cause by priority, and tallied. The largest bucket is 'no clear cause' with 34 of the top 100 errors (34%). 47% of these big errors are under-forecasts (stockout risk). I left a `manual_cause` column for manual review in Excel.

**21. Does the neural network beat the baseline?**
The MLP beats the best baseline (Exp. smoothing) on the untouched test weeks: WAPE 10.1% vs 11.4% (11.1% relative improvement, and even its worst random seed beats the baseline). But plain linear regression with the same features already gets 10.2% (10.0% better than the baseline); the hidden layers add only 1.3% on top of that - below the bar, so the extra complexity is not justified. **Final model: Linear regression.** It earned its place on the dev set and was confirmed on test. The honest message: complexity has to be paid for with accuracy *and* interpretability.

**22. How do you diagnose bias vs variance with a baseline as proxy?**
Avoidable bias = train error - proxy error; variance = dev error - train error. Here avoidable bias = -2.1% and variance = 0.7%. The model already beats the baseline proxy on the training weeks and generalises: bias and variance are both small. Remaining error is likely noise or information these features do not contain.

### Neural-network basics

**23. Explain forward and back propagation in your MLP.**
Forward: `Z = A_prev W + b`, ReLU on hidden layers, linear output. Loss: mean of 0.5 x squared error + (lambda/2) x sum of squared weights. Backward: output gradient `(y_hat - y)/m`, then for each layer `dW = A_prev^T dZ + lambda W`, `dA_prev = dZ W^T`, and multiply by the ReLU derivative. All in `src/nn_numpy.py`.

**24. Why ReLU and He initialisation?**
ReLU avoids vanishing gradients and is cheap. He initialisation draws weights with variance 2/n_in, which keeps the signal scale stable through ReLU layers.

**25. How do you fight overfitting?**
L2 regularisation, optional dropout, early stopping on dev (best epoch 45), a small network (305 weights), and watching the train/dev learning curves.

**26. What is gradient checking and why did my first attempt fail?**
Compare backprop gradients with `(L(w+e) - L(w-e)) / 2e`; the relative difference should be below about 1e-6. With all-zero biases a ReLU unit can sit exactly at 0 where the derivative is undefined, so the check disagreed; using non-zero biases fixed it - the check was pointing at a real subtlety, not a bug in backprop (see the comment in `tests/test_nn_gradcheck.py`).

**27. Mini-batch, Adam?**
Mini-batches give noisy but cheap gradient estimates and faster progress than full-batch; Adam keeps running averages of the gradient (momentum) and its square (per-weight step size) with bias correction.

**28. Why normalise inputs with train statistics?**
Features on very different scales slow and destabilise training; using dev/test statistics would leak information from the future.

## 6. Limitations and next steps

- Real data: add missing history, structural breaks, stockout-censored demand correction.
- Multi-step (lead-time-ahead) forecasts and probabilistic forecasts (prediction intervals) feeding safety stock directly.
- Add a cost model (holding vs shortage cost) to optimise service level per ABC class.
- Hierarchical/category-level models for sparse SKUs; segment-level model choice using the segment WAPE table.
- Power BI dashboard on `outputs/dashboard/` (star-schema CSVs are ready) and a scheduled refresh.
