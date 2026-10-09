-- =====================================================================
-- 03  ABC analysis (Pareto) with window functions
-- A = items making up the first 80% of revenue, B = next 15%, C = last 5%.
-- The share BEFORE each item is used so the item crossing the 80% line stays an A.
-- =====================================================================

-- name: abc_classification
WITH rev AS (
    SELECT p.sku, p.category, p.unit_price,
           SUM(d.units_fulfilled * p.unit_price) AS revenue
    FROM demand_daily d JOIN products p ON p.sku = d.sku
    GROUP BY p.sku, p.category, p.unit_price
),
cum AS (
    SELECT sku, category, revenue,
           SUM(revenue) OVER (ORDER BY revenue DESC, sku
                              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_revenue,
           SUM(revenue) OVER ()                                                    AS total_revenue
    FROM rev
)
SELECT sku, category, ROUND(revenue, 2) AS revenue,
       ROUND(100.0 * revenue / total_revenue, 2)                 AS revenue_pct,
       ROUND(100.0 * cum_revenue / total_revenue, 2)             AS cumulative_pct,
       CASE WHEN (cum_revenue - revenue) / total_revenue < 0.80 THEN 'A'
            WHEN (cum_revenue - revenue) / total_revenue < 0.95 THEN 'B'
            ELSE 'C' END                                         AS abc_class
FROM cum
ORDER BY revenue DESC, sku;

-- name: abc_summary
-- How many SKUs / how much revenue / how much inventory sits in each class?
WITH rev AS (
    SELECT sku, SUM(units_fulfilled * unit_price) AS revenue
    FROM demand_daily JOIN products USING (sku) GROUP BY sku
),
cls AS (
    SELECT sku, revenue,
           CASE WHEN (SUM(revenue) OVER (ORDER BY revenue DESC, sku ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) - revenue)
                     / SUM(revenue) OVER () < 0.80 THEN 'A'
                WHEN (SUM(revenue) OVER (ORDER BY revenue DESC, sku ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) - revenue)
                     / SUM(revenue) OVER () < 0.95 THEN 'B'
                ELSE 'C' END AS abc_class
    FROM rev
),
stock AS (
    SELECT sku, AVG(day_units) AS avg_units
    FROM (SELECT sku, date, SUM(on_hand_units) AS day_units FROM inventory_daily GROUP BY sku, date)
    GROUP BY sku
)
SELECT c.abc_class,
       COUNT(*)                                                         AS n_skus,
       ROUND(SUM(c.revenue), 0)                                         AS revenue,
       ROUND(100.0 * SUM(c.revenue) / SUM(SUM(c.revenue)) OVER (), 1)    AS revenue_pct,
       ROUND(SUM(s.avg_units * p.unit_cost), 0)                         AS avg_inventory_value,
       ROUND(100.0 * SUM(s.avg_units * p.unit_cost)
             / SUM(SUM(s.avg_units * p.unit_cost)) OVER (), 1)           AS inventory_pct
FROM cls c
JOIN stock    s ON s.sku = c.sku
JOIN products p ON p.sku = c.sku
GROUP BY c.abc_class ORDER BY c.abc_class;
