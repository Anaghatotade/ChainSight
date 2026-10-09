-- =====================================================================
-- 02  Window-function queries (LAG, moving average, RANK, ROW_NUMBER, running totals)
-- =====================================================================

-- name: weekly_demand_wow_growth
-- Weekly company demand, week-over-week growth (LAG) and a 4-week moving average.
WITH weekly AS (
    SELECT date(d.date, '-' || ((CAST(strftime('%w', d.date) AS INTEGER) + 6) % 7) || ' days') AS week_start,
           SUM(d.units_demanded) AS units
    FROM demand_daily d
    GROUP BY week_start
)
SELECT week_start,
       units,
       LAG(units) OVER (ORDER BY week_start)                                     AS prev_week_units,
       ROUND(100.0 * (units - LAG(units) OVER (ORDER BY week_start))
             / LAG(units) OVER (ORDER BY week_start), 2)                         AS wow_growth_pct,
       ROUND(AVG(units) OVER (ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW), 1) AS moving_avg_4w
FROM weekly
ORDER BY week_start;

-- name: top3_skus_per_category
-- ROW_NUMBER() inside each category: the 3 biggest revenue SKUs + their share of the category.
WITH sku_rev AS (
    SELECT p.category, p.sku, SUM(d.units_fulfilled * p.unit_price) AS revenue
    FROM demand_daily d JOIN products p ON p.sku = d.sku
    GROUP BY p.category, p.sku
),
ranked AS (
    SELECT category, sku, revenue,
           ROW_NUMBER() OVER (PARTITION BY category ORDER BY revenue DESC, sku) AS rank_in_category,
           ROUND(100.0 * revenue / SUM(revenue) OVER (PARTITION BY category), 1)   AS pct_of_category
    FROM sku_rev
)
SELECT * FROM ranked WHERE rank_in_category <= 3 ORDER BY category, rank_in_category;

-- name: monthly_stockouts_running_total
-- Stockout-days per warehouse per month and the running total (SUM OVER).
WITH m AS (
    SELECT warehouse_code, substr(date, 1, 7) AS month, SUM(stockout_flag) AS stockout_days
    FROM demand_daily GROUP BY warehouse_code, substr(date, 1, 7)
)
SELECT warehouse_code, month, stockout_days,
       SUM(stockout_days) OVER (PARTITION BY warehouse_code ORDER BY month
                                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_stockout_days
FROM m ORDER BY warehouse_code, month;

-- name: sku_growth_first_vs_second_year
-- Year-over-year growth per SKU, then ranked with RANK() - which SKUs are really growing / shrinking?
WITH yearly AS (
    SELECT sku,
           SUM(CASE WHEN date <  '2025-01-01' THEN units_demanded ELSE 0 END) AS units_2024,
           SUM(CASE WHEN date >= '2025-01-01' THEN units_demanded ELSE 0 END) AS units_2025
    FROM demand_daily GROUP BY sku
)
SELECT sku, units_2024, units_2025,
       ROUND(100.0 * (units_2025 - units_2024) / units_2024, 1)                              AS yoy_growth_pct,
       RANK() OVER (ORDER BY 1.0 * (units_2025 - units_2024) / units_2024 DESC)               AS growth_rank
FROM yearly ORDER BY growth_rank;

-- name: supplier_lead_time_trend
-- LAG per supplier: is the supplier getting slower from one PO to the next?
WITH po AS (
    SELECT supplier_code, order_date, actual_lead_days,
           LAG(actual_lead_days) OVER (PARTITION BY supplier_code ORDER BY order_date, po_number) AS prev_lead
    FROM purchase_orders WHERE actual_lead_days IS NOT NULL
)
SELECT supplier_code,
       COUNT(*)                                       AS n_pos,
       ROUND(AVG(actual_lead_days - prev_lead), 2)    AS avg_change_vs_previous_po_days
FROM po WHERE prev_lead IS NOT NULL
GROUP BY supplier_code ORDER BY avg_change_vs_previous_po_days DESC;
