# Business recommendations (generated from the data)

### 1. Fix the top lost-revenue SKUs first | Value at stake: $7.97M (lost revenue, whole period)
**Finding:** The top 15 SKUs account for 74% of all lost revenue (15 of them are A items); the worst is SKU-00049 with $1.49M.

**Action:** Run a weekly stockout review on these 15 SKUs: confirm lead time, check open POs, raise reorder points before touching the long tail.

**Track:** Lost revenue of top-15 SKUs

### 2. Reorder policy refresh | Value at stake: $2.30M (lost revenue, last 13 weeks)
**Finding:** Fill rate fell from 92.9% (first 3 months) to 78.7% (last 3 months) while demand grew 12.0% year on year. 164 of 180 SKU-warehouses (91%) have a reorder point below what current demand and actual lead times require; they run a 19.7% stockout-day rate vs 2.1% for the rest.

**Action:** Re-calculate safety stock and reorder point every quarter from the last 13 weeks of demand and the supplier's ACTUAL lead time and its variability. Phase 1: the 20 SKU-warehouses that lost the most revenue in the last 13 weeks ($1.61M, 70% of the total) need about $411K of extra safety stock (59% of today's average inventory value).

**Track:** Fill rate, stockout-day rate, inventory turnover

### 3. ABC-differentiated service levels | Value at stake: $8.81M (A-class lost revenue, whole period)
**Finding:** A items are 28% of SKUs but 81% of revenue and 82% of lost revenue, yet their fill rate (85.7%) is within 0.8 percentage points of C items (85.0%): every SKU gets the same service-level target.

**Action:** Set service targets by class (for example 98% for A, 95% for B, 90% for C). C items hold only 4.9% of inventory value, so the extra A-item stock has to be budgeted, not funded by trimming C.

**Track:** Fill rate by ABC class, lost revenue in class A

### 4. Supplier lead-time reliability
**Finding:** Only 53.1% of delivered POs arrive on or before the promised date; late POs are 5.0 days late on average. On-time rate ranges from 39.6% (SUP-012) to 68.1% (SUP-015); 5 of 24 suppliers are below 50% on-time.

**Action:** Start a monthly supplier scorecard (on-time %, delay days, lead-time CV), escalate the bottom suppliers, and use measured lead time + variability (not the quoted lead time) in safety-stock formulas.

**Track:** On-time delivery %, lead-time CV by supplier

### 5. Expediting cost | Value at stake: $721K (extra freight vs non-air rates, whole period)
**Finding:** 31% of POs ship by air at 12.0% of goods value vs 4.5% for other modes - about $721K of extra freight over the period.

**Action:** Fewer emergency orders: earlier reorder triggers (see policy refresh) are cheaper than air freight. Review air shipments by SKU and keep air only for A items.

**Track:** Air-freight share of POs, freight % of PO value

### 6. Promotion planning
**Finding:** Promo weeks run at 1.23x the previous 8-week average (normal weeks 0.98x). Stockout rate on promo days is 15.4% vs 12.9% on normal days.

**Action:** Share the promotion calendar with planning and add the promo flag to the forecast (it is the planned, known input the baselines ignore). Build stock one lead time BEFORE a promo.

**Track:** Stockout rate on promo days

### 7. Seasonal stock planning
**Finding:** Electronics swings 0.65 index points between its peak (Aug, 1.30) and low (Feb, 0.66) month; category peaks fall in different months.

**Action:** Adjust reorder points by the monthly seasonal index, so stock is built ahead of each category's peak rather than a flat yearly parameter.

**Track:** Fill rate in peak months by category

### 8. Forecasting model choice
**Finding:** On the untouched test weeks the best baseline (Exp. smoothing) has WAPE 11.4%, linear regression 10.2% and the MLP 10.1%. The MLP beats the best baseline, but adds only 1.3% relative improvement over linear regression. Chosen model: Linear regression.

**Action:** Use Linear regression for weekly forecasts (promo flag + recent demand + month), keep the Exp. smoothing as the fallback and the MLP as a challenger to re-test each quarter.

**Track:** WAPE, bias on a rolling basis

### 9. Forecast accuracy -> safety stock
**Finding:** Using the MLP's forecast errors instead of the Exp. smoothing's changes the indicative safety-stock requirement by -14.8% ($176K -> $150K).

**Action:** Size safety stock from forecast error (not raw demand variability) once the forecast is live; track the realised error each month.

**Track:** Forecast error std per SKU, safety-stock value

### 10. Data quality at the source
**Finding:** Cleaning corrected or removed 5,998 records (duplicates, impossible values, mixed formats).

**Action:** Add input validation in the ERP export: unique keys, non-negative quantities, ISO dates, controlled category lists.

**Track:** Rows rejected by validation per load
