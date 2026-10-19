# Business recommendations (generated from the data)

_Evidence: **measured** = computed from the real M5 data; **assumption-based** = uses an assumed lead time (see config.py)._

### 1. Plan by ABC class: put the effort where the revenue is | Value at stake: $149.9M (revenue of A items, whole period)
_Evidence: measured_

**Finding:** 1,264 A items (41% of items) make 80% of revenue; the 862 C items (28%) make only 5%. The single best item (FOODS_3_586) is $1.5M, but the top 100 items are only 23% of revenue: this is a long, flat catalogue, not a handful of stars.

**Action:** Review A items weekly with a tight service target, B items every 2-4 weeks, and manage C items by exception. Because 'A' is a wide group here, split it again by demand variability (ABC x CV matrix) before setting stock rules.

**Track:** Revenue and zero-sales weeks by ABC class

### 2. Rationalise the slow tail | Value at stake: $5.3M (revenue of the slow C items (what a delisting would put at risk))
_Evidence: measured_

**Finding:** 553 C items (64% of all C items) are slow movers (no sale in more than 30% of their listed weeks) with only 2.9% of total revenue. C items have no sale in 37% of the weeks they are listed, vs 15% for A items.

**Action:** Review these slow C items for delisting or for a lower store footprint, and stock the rest to order-on-demand or larger, less frequent batches. Check first that they are not enablers (basket items) the data cannot show.

**Track:** Share of listed weeks with zero sales; revenue per listed item

### 3. Safety stock by item class (assumption-based) | Value at stake: $826K (safety stock at retail value (assumption-based))
_Evidence: assumption-based_

**Finding:** ASSUMPTION: 1-week lead time and review, 95% cycle service (config.py). On the real demand variability this implies about $826K of safety stock at retail value for 9,147 item-state series; A items hold 71% of it. Erratic series are 9% of series but need 12% of the safety stock (median cover 2.2 weeks vs 0.7 for stable series). Giving A / B / C different service targets (97% / 95% / 90%) changes the total by 7.7%.

**Action:** Replace one flat service factor by class- and variability-specific factors, and replace the lead-time assumption with real supplier lead times as soon as they are available.

**Track:** Safety-stock weeks of cover by class

### 4. Plan around the calendar: SNAP days, events, weekdays
_Evidence: measured_

**Finding:** In FOODS, SNAP benefit days lift units to 1.10x (CA) up to 1.30x (WI) of non-SNAP days; the effect on other categories is at most 1.04x. 4 of 26 named events sell at least 5% above normal neighbouring days (best: LaborDay, 1.28x) and 7 at least 5% below (lowest: Thanksgiving, 0.74x). Saturday is 1.40x the lowest weekday (Wednesday).

**Action:** Load the state-specific SNAP calendar, the event calendar and a weekday profile into replenishment and staffing plans, and build stock for FOODS ahead of SNAP days state by state.

**Track:** Units on SNAP vs non-SNAP days by state

### 5. Seasonal stock planning
_Evidence: measured_

**Finding:** HOBBIES_2 swings 0.63 index points between its peak (Oct, 1.40) and low (Jul, 0.77) month; the three categories swing only 0.16 (FOODS), 0.17 (HOUSEHOLD) and 0.17 (HOBBIES) overall, with peaks in Jun, Sep and Feb.

**Action:** Apply monthly seasonal indices at department level instead of a flat yearly parameter, starting with the most seasonal department.

**Track:** Forecast bias by month

### 6. Price cuts: test before you scale
_Evidence: measured_

**Finding:** Price-cut weeks are rare (0.59% of item-state weeks). In those weeks the typical item sells 1.15x its previous 8-week average (normal weeks 0.96x) - but the mean is 2.81x, so the average is pulled up by a few items that jump a lot. This is an association: cuts may be timed with seasons and events.

**Action:** Run a controlled price test (similar stores, with and without the cut) before basing a stock-up rule on this uplift; when a cut is planned, add it to the forecast as a known input.

**Track:** Unit uplift in test vs control stores

### 7. Forecasting model choice
_Evidence: measured_

**Finding:** On the untouched test weeks the best baseline (Exp. smoothing) has WAPE 25.0%, linear regression 26.1% and the MLP 24.5%. The MLP is slightly better than the best baseline but misses the bar we set in advance (2.3% relative gain; required: 5%). Chosen model: Exp. smoothing.

**Action:** Use Exp. smoothing for weekly forecasts; keep the MLP as a challenger and re-test it each quarter, and look for new information (price plans, events, stock availability) rather than a bigger network.

**Track:** WAPE and bias, rolling

### 8. What forecast accuracy could mean for stock (simulation, assumption-based) | Value at stake: $88K (difference in average inventory (simulation))
_Evidence: assumption-based_

**Finding:** ASSUMPTION: 1-week lead and review period. In a replay of the real test weeks, a policy using the MLP forecast reaches 95% fill with $557K of average inventory vs $646K for the Exp. smoothing policy (-13.7% change). That is a bigger gap than the 2.3% WAPE gap, because safety stock follows the spread of forecast errors (retail-value weighted, the MLP's spread is 7.6% lower). Treat it as indicative, not as a result: it depends on the assumed lead time and on observed sales being true demand (lost sales are invisible).

**Action:** Do not switch models on this alone. If a pilot with real stock and lead-time data shows a similar gap, the MLP's small accuracy edge would be worth its extra effort.

**Track:** Inventory needed for a target fill rate

### 9. Close the data gap: record stock and stockouts
_Evidence: measured_

**Finding:** 21% of item-store-weeks have no price (item not yet on sale); 24% of listed weeks have zero sales, and with no stock-on-hand data a zero cannot be told apart from a stockout. So fill rate, turnover and days of inventory cannot be measured from this data.

**Action:** Capture weekly on-hand stock, stockout flags, purchase prices and supplier lead times next to the sales data; with them the service and inventory KPIs become measurable.

**Track:** Share of sales rows with stock-on-hand recorded
