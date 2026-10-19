-- =====================================================================
-- 05  Calendar and price effects: weekday pattern, SNAP days, events, price changes
-- (These are ASSOCIATIONS in observational data, not causal effects - the README says so too.)
-- =====================================================================

-- name: weekday_index
-- Average units per weekday relative to the all-days average (1.00 = average day).
WITH day AS (
    SELECT d.date, d.weekday, d.wday, SUM(f.units) AS units
    FROM fact_daily_sales f JOIN dim_date d USING (date) GROUP BY d.date, d.weekday, d.wday
)
SELECT weekday, wday, ROUND(AVG(units), 0) AS avg_daily_units,
       ROUND(AVG(units) / (SELECT AVG(units) FROM day), 3) AS weekday_index
FROM day GROUP BY weekday, wday ORDER BY wday;

-- name: snap_day_effect
-- Average daily units on SNAP-benefit days vs other days, per state and category.
-- SNAP days fall early in the month, so part of any difference is the normal "start of month" pattern.
WITH d AS (
    SELECT f.date, s.state_id,
           CASE WHEN f.dept_id LIKE 'FOODS%' THEN 'FOODS' WHEN f.dept_id LIKE 'HOBBIES%' THEN 'HOBBIES' ELSE 'HOUSEHOLD' END AS cat_id,
           CASE s.state_id WHEN 'CA' THEN dd.snap_CA WHEN 'TX' THEN dd.snap_TX ELSE dd.snap_WI END AS snap,
           SUM(f.units) AS units
    FROM fact_daily_sales f JOIN dim_store s USING (store_key) JOIN dim_date dd USING (date)
    GROUP BY f.date, s.state_id, cat_id, snap
)
SELECT state_id, cat_id AS category, SUM(snap) AS snap_days,
       ROUND(AVG(CASE WHEN snap = 1 THEN units END), 0) AS avg_units_snap_day,
       ROUND(AVG(CASE WHEN snap = 0 THEN units END), 0) AS avg_units_other_day,
       ROUND(AVG(CASE WHEN snap = 1 THEN units END) / AVG(CASE WHEN snap = 0 THEN units END), 3) AS snap_ratio
FROM d GROUP BY state_id, cat_id ORDER BY state_id, cat_id;

-- name: event_uplift_by_type
-- Event day total units divided by the average of the SAME weekday one week before and one week after
-- (neighbour days must be event-free). That controls for weekday pattern and for trend/season.
WITH day AS (
    SELECT d.date, d.wday, d.week_idx, d.event_name_1, d.event_type_1, SUM(f.units) AS units
    FROM fact_daily_sales f JOIN dim_date d USING (date)
    GROUP BY d.date, d.wday, d.week_idx, d.event_name_1, d.event_type_1
),
nb AS (
    SELECT *, LAG(units)  OVER (PARTITION BY wday ORDER BY week_idx) AS prev_units,
              LEAD(units) OVER (PARTITION BY wday ORDER BY week_idx) AS next_units,
              LAG(event_name_1)  OVER (PARTITION BY wday ORDER BY week_idx) AS prev_event,
              LEAD(event_name_1) OVER (PARTITION BY wday ORDER BY week_idx) AS next_event
    FROM day
)
SELECT event_type_1 AS event_type, COUNT(*) AS n_event_days,
       ROUND(AVG(units * 2.0 / (prev_units + next_units)), 3) AS avg_ratio_vs_same_weekday_neighbours
FROM nb
WHERE event_name_1 IS NOT NULL AND prev_units IS NOT NULL AND next_units IS NOT NULL
  AND prev_event IS NULL AND next_event IS NULL
GROUP BY event_type_1 ORDER BY avg_ratio_vs_same_weekday_neighbours DESC;

-- name: event_uplift_by_event
WITH day AS (
    SELECT d.date, d.wday, d.week_idx, d.event_name_1, SUM(f.units) AS units
    FROM fact_daily_sales f JOIN dim_date d USING (date)
    GROUP BY d.date, d.wday, d.week_idx, d.event_name_1
),
nb AS (
    SELECT *, LAG(units)  OVER (PARTITION BY wday ORDER BY week_idx) AS prev_units,
              LEAD(units) OVER (PARTITION BY wday ORDER BY week_idx) AS next_units,
              LAG(event_name_1)  OVER (PARTITION BY wday ORDER BY week_idx) AS prev_event,
              LEAD(event_name_1) OVER (PARTITION BY wday ORDER BY week_idx) AS next_event
    FROM day
)
SELECT event_name_1 AS event, COUNT(*) AS n_occurrences,
       ROUND(AVG(units * 2.0 / (prev_units + next_units)), 3) AS avg_ratio_vs_same_weekday_neighbours
FROM nb
WHERE event_name_1 IS NOT NULL AND prev_units IS NOT NULL AND next_units IS NOT NULL
  AND prev_event IS NULL AND next_event IS NULL
GROUP BY event_name_1 ORDER BY avg_ratio_vs_same_weekday_neighbours DESC;

-- name: price_change_frequency
-- How often does an item-store change its price from one week to the next? (LAG over each item-store's weeks)
WITH p AS (
    SELECT item_key, week_idx, sell_price,
           LAG(sell_price) OVER (PARTITION BY item_key, store_key ORDER BY week_idx) AS prev_price,
           LAG(week_idx)   OVER (PARTITION BY item_key, store_key ORDER BY week_idx) AS prev_week
    FROM fact_weekly_sales
)
SELECT i.cat_id AS category, COUNT(*) AS comparable_weeks,
       ROUND(100.0 * AVG(p.sell_price < p.prev_price), 2) AS price_cut_week_pct,
       ROUND(100.0 * AVG(p.sell_price > p.prev_price), 2) AS price_rise_week_pct,
       ROUND(100.0 * AVG(p.sell_price <> p.prev_price), 2) AS price_change_week_pct
FROM p JOIN dim_item i USING (item_key)
WHERE p.prev_week = p.week_idx - 1
GROUP BY i.cat_id ORDER BY i.cat_id;
