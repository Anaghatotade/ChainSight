-- =====================================================================
-- 01  KPI queries  (joins + aggregation)
-- Each query starts with "-- name: <query_name>"; src/04_run_sql_kpis.py runs them
-- and saves every result to outputs/sql_results/.
-- =====================================================================

-- name: kpi_overall
-- Headline KPIs for the whole business.
WITH sales AS (
    SELECT SUM(d.units_demanded)                      AS units_demanded,
           SUM(d.units_fulfilled)                     AS units_fulfilled,
           AVG(d.stockout_flag)                       AS stockout_rate,
           SUM(d.units_fulfilled * p.unit_price)      AS revenue,
           SUM((d.units_demanded - d.units_fulfilled) * p.unit_price) AS lost_revenue,
           SUM(d.units_fulfilled * p.unit_cost)       AS cogs,
           COUNT(DISTINCT d.date)                     AS n_days
    FROM demand_daily d
    JOIN products p ON p.sku = d.sku
),
inv_by_day AS (                                       -- total inventory value on each day
    SELECT i.date, SUM(i.on_hand_units * p.unit_cost) AS inv_value, SUM(i.on_hand_units) AS inv_units
    FROM inventory_daily i
    JOIN products p ON p.sku = i.sku
    GROUP BY i.date
),
inv AS (SELECT AVG(inv_value) AS avg_inv_value, AVG(inv_units) AS avg_inv_units FROM inv_by_day)
SELECT s.units_demanded,
       s.revenue,
       s.lost_revenue,
       1.0 * s.units_fulfilled / s.units_demanded                AS fill_rate,
       s.stockout_rate,
       inv.avg_inv_value                                        AS avg_inventory_value,
       s.cogs * (365.0 / s.n_days) / inv.avg_inv_value          AS inventory_turnover,
       inv.avg_inv_units / (1.0 * s.units_fulfilled / s.n_days) AS days_of_inventory
FROM sales s CROSS JOIN inv;

-- name: kpi_by_category
SELECT p.category,
       SUM(d.units_demanded)                                    AS units_demanded,
       SUM(d.units_fulfilled * p.unit_price)                    AS revenue,
       1.0 * SUM(d.units_fulfilled) / SUM(d.units_demanded)     AS fill_rate,
       AVG(d.stockout_flag)                                     AS stockout_rate
FROM demand_daily d
JOIN products p ON p.sku = d.sku
GROUP BY p.category
ORDER BY fill_rate;

-- name: kpi_by_warehouse
SELECT w.warehouse_code, w.region,
       SUM(d.units_demanded)                                    AS units_demanded,
       SUM(d.units_fulfilled * p.unit_price)                    AS revenue,
       1.0 * SUM(d.units_fulfilled) / SUM(d.units_demanded)     AS fill_rate,
       AVG(d.stockout_flag)                                     AS stockout_rate
FROM demand_daily d
JOIN products   p ON p.sku = d.sku
JOIN warehouses w ON w.warehouse_code = d.warehouse_code
GROUP BY w.warehouse_code, w.region
ORDER BY fill_rate;

-- name: kpi_monthly
SELECT substr(d.date, 1, 7)                                     AS month,
       SUM(d.units_demanded)                                    AS units_demanded,
       SUM(d.units_fulfilled * p.unit_price)                    AS revenue,
       1.0 * SUM(d.units_fulfilled) / SUM(d.units_demanded)     AS fill_rate,
       AVG(d.stockout_flag)                                     AS stockout_rate
FROM demand_daily d
JOIN products p ON p.sku = d.sku
GROUP BY substr(d.date, 1, 7)
ORDER BY month;

-- name: kpi_by_sku
-- Per-SKU fill rate, turnover and days of inventory (two CTEs joined on sku).
WITH sales AS (
    SELECT d.sku,
           SUM(d.units_demanded)  AS units_demanded,
           SUM(d.units_fulfilled) AS units_fulfilled,
           AVG(d.stockout_flag)   AS stockout_rate,
           COUNT(DISTINCT d.date) AS n_days
    FROM demand_daily d GROUP BY d.sku
),
stock AS (                                             -- average (all-warehouse) units on hand per day
    SELECT sku, AVG(day_units) AS avg_units
    FROM (SELECT sku, date, SUM(on_hand_units) AS day_units FROM inventory_daily GROUP BY sku, date)
    GROUP BY sku
)
SELECT s.sku, p.category,
       1.0 * s.units_fulfilled / s.units_demanded                                   AS fill_rate,
       s.stockout_rate,
       st.avg_units * p.unit_cost                                                    AS avg_inventory_value,
       (s.units_fulfilled * p.unit_cost) * (365.0 / s.n_days) / (st.avg_units * p.unit_cost) AS inventory_turnover,
       st.avg_units / (1.0 * s.units_fulfilled / s.n_days)                           AS days_of_inventory
FROM sales s
JOIN stock    st ON st.sku = s.sku
JOIN products p  ON p.sku  = s.sku
ORDER BY s.sku;
