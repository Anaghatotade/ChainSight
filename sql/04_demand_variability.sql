-- =====================================================================
-- 04  Demand variability and intermittency (replaces the old stockout queries: the M5 data has no inventory)
-- Level = item x state (what a regional distribution centre forecasts). Weekly units are summed over the state's stores.
-- CV = standard deviation / mean of weekly units (population std; SQLite has no STDDEV, so sqrt(E[x^2] - E[x]^2)).
-- A "zero week" is an ON-SALE week with no units - NOT a stockout (we cannot see stock), just no sales.
-- =====================================================================

-- name: item_state_demand_profile
WITH st AS (
    SELECT f.item_key, s.state_id, f.week_idx, SUM(f.units) AS units, SUM(f.revenue) AS revenue
    FROM fact_weekly_sales f JOIN dim_store s USING (store_key)
    GROUP BY f.item_key, s.state_id, f.week_idx
),
prof AS (
    SELECT item_key, state_id, COUNT(*) AS weeks_on_sale, AVG(units) AS mean_units, AVG(1.0 * units * units) AS mean_sq,
           100.0 * AVG(units = 0) AS zero_week_pct, SUM(revenue) AS revenue
    FROM st GROUP BY item_key, state_id
)
SELECT i.item_id, p.state_id, i.cat_id AS category, p.weeks_on_sale, ROUND(p.mean_units, 4) AS mean_weekly_units,
       ROUND(SQRT(MAX(p.mean_sq - p.mean_units * p.mean_units, 0)), 4) AS std_weekly_units,
       ROUND(SQRT(MAX(p.mean_sq - p.mean_units * p.mean_units, 0)) / p.mean_units, 4) AS cv,
       ROUND(p.zero_week_pct, 2) AS zero_week_pct, ROUND(p.revenue, 2) AS revenue
FROM prof p JOIN dim_item i USING (item_key)
WHERE p.mean_units > 0
ORDER BY p.revenue DESC, i.item_id, p.state_id;

-- name: demand_profile_by_category
WITH st AS (
    SELECT f.item_key, s.state_id, f.week_idx, SUM(f.units) AS units
    FROM fact_weekly_sales f JOIN dim_store s USING (store_key)
    GROUP BY f.item_key, s.state_id, f.week_idx
),
prof AS (
    SELECT item_key, state_id, COUNT(*) AS weeks_on_sale, AVG(units) AS mean_units, AVG(1.0 * units * units) AS mean_sq,
           100.0 * AVG(units = 0) AS zero_week_pct
    FROM st GROUP BY item_key, state_id
),
banded AS (
    SELECT i.cat_id, p.zero_week_pct,
           SQRT(MAX(p.mean_sq - p.mean_units * p.mean_units, 0)) / p.mean_units AS cv
    FROM prof p JOIN dim_item i USING (item_key) WHERE p.mean_units > 0
)
SELECT cat_id AS category, COUNT(*) AS n_item_states,
       ROUND(AVG(cv), 3) AS mean_cv,
       SUM(cv < 0.5) AS n_stable, SUM(cv >= 0.5 AND cv < 1.0) AS n_variable, SUM(cv >= 1.0) AS n_erratic,
       ROUND(AVG(zero_week_pct), 2) AS mean_zero_week_pct
FROM banded GROUP BY cat_id ORDER BY cat_id;
