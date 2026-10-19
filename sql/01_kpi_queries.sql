-- =====================================================================
-- 01  Core business KPIs (plain SQL: JOIN, GROUP BY, CASE)
-- Grain reminder: fact_weekly_sales = one row per item x store x week in which the item was ON SALE.
-- Money = units x sell_price (retail revenue; the M5 data has no cost or margin).
-- =====================================================================

-- name: overall_kpis
SELECT (SELECT COUNT(*) FROM dim_item)  AS n_items,
       (SELECT COUNT(*) FROM dim_store) AS n_stores,
       (SELECT COUNT(*) FROM dim_week)  AS n_weeks,
       COUNT(*)                         AS on_sale_series_weeks,
       SUM(units)                       AS total_units,
       ROUND(SUM(revenue), 2)           AS total_revenue,
       ROUND(SUM(revenue) / SUM(units), 4)            AS avg_selling_price,
       ROUND(100.0 * SUM(units = 0) / COUNT(*), 2)    AS zero_sales_week_pct
FROM fact_weekly_sales;

-- name: revenue_by_category
SELECT i.cat_id AS category,
       COUNT(DISTINCT i.item_key)                     AS n_items,
       SUM(f.units)                                   AS units,
       ROUND(SUM(f.revenue), 2)                       AS revenue,
       ROUND(100.0 * SUM(f.revenue) / SUM(SUM(f.revenue)) OVER (), 2) AS revenue_share_pct,
       ROUND(SUM(f.revenue) / SUM(f.units), 3)        AS avg_selling_price
FROM fact_weekly_sales f JOIN dim_item i USING (item_key)
GROUP BY i.cat_id
ORDER BY revenue DESC;

-- name: revenue_by_department
SELECT i.dept_id AS department, i.cat_id AS category,
       COUNT(DISTINCT i.item_key) AS n_items,
       SUM(f.units) AS units, ROUND(SUM(f.revenue), 2) AS revenue,
       ROUND(100.0 * SUM(f.revenue) / SUM(SUM(f.revenue)) OVER (), 2) AS revenue_share_pct
FROM fact_weekly_sales f JOIN dim_item i USING (item_key)
GROUP BY i.dept_id, i.cat_id
ORDER BY revenue DESC;

-- name: revenue_by_store
SELECT s.store_id, s.state_id, SUM(f.units) AS units, ROUND(SUM(f.revenue), 2) AS revenue,
       ROUND(100.0 * SUM(f.revenue) / SUM(SUM(f.revenue)) OVER (), 2) AS revenue_share_pct,
       COUNT(DISTINCT f.item_key) AS items_sold
FROM fact_weekly_sales f JOIN dim_store s USING (store_key)
GROUP BY s.store_id, s.state_id
ORDER BY revenue DESC;

-- name: revenue_by_state_category
SELECT s.state_id, i.cat_id AS category, SUM(f.units) AS units, ROUND(SUM(f.revenue), 2) AS revenue,
       ROUND(100.0 * SUM(f.revenue) / SUM(SUM(f.revenue)) OVER (PARTITION BY s.state_id), 2) AS share_of_state_pct
FROM fact_weekly_sales f JOIN dim_store s USING (store_key) JOIN dim_item i USING (item_key)
GROUP BY s.state_id, i.cat_id
ORDER BY s.state_id, revenue DESC;

-- name: yearly_sales
-- 2011 and 2016 are partial years, so the fair comparison column is revenue per week.
WITH weekly AS (
    SELECT week_idx, SUM(units) AS units, SUM(revenue) AS revenue FROM fact_weekly_sales GROUP BY week_idx
)
SELECT w.year, COUNT(*) AS n_weeks, SUM(weekly.units) AS units, ROUND(SUM(weekly.revenue), 2) AS revenue,
       ROUND(SUM(weekly.revenue) / COUNT(*), 2) AS revenue_per_week
FROM weekly JOIN dim_week w USING (week_idx)
GROUP BY w.year ORDER BY w.year;

-- name: monthly_sales
WITH weekly AS (
    SELECT week_idx, SUM(units) AS units, SUM(revenue) AS revenue FROM fact_weekly_sales GROUP BY week_idx
)
SELECT w.year, w.month, COUNT(*) AS n_weeks, SUM(weekly.units) AS units, ROUND(SUM(weekly.revenue), 2) AS revenue,
       ROUND(SUM(weekly.revenue) / COUNT(*), 2) AS revenue_per_week
FROM weekly JOIN dim_week w USING (week_idx)
GROUP BY w.year, w.month ORDER BY w.year, w.month;

-- name: price_band_summary
-- Items bucketed by their average selling price (revenue / units).
WITH item AS (
    SELECT item_key, SUM(units) AS units, SUM(revenue) AS revenue FROM fact_weekly_sales GROUP BY item_key
)
SELECT CASE WHEN revenue / units < 2  THEN '1 under $2'
            WHEN revenue / units < 5  THEN '2 $2 to $5'
            WHEN revenue / units < 10 THEN '3 $5 to $10'
            ELSE '4 $10 and above' END AS price_band,
       COUNT(*) AS n_items, SUM(units) AS units, ROUND(SUM(revenue), 2) AS revenue,
       ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 2) AS revenue_share_pct
FROM item WHERE units > 0
GROUP BY 1 ORDER BY 1;

-- name: top20_items_by_revenue
SELECT i.item_id, i.dept_id, SUM(f.units) AS units, ROUND(SUM(f.revenue), 2) AS revenue,
       ROUND(SUM(f.revenue) / SUM(f.units), 2) AS avg_selling_price
FROM fact_weekly_sales f JOIN dim_item i USING (item_key)
GROUP BY i.item_id, i.dept_id
ORDER BY revenue DESC, i.item_id
LIMIT 20;
