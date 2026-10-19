-- =====================================================================
-- 03  ABC analysis (Pareto) with window functions
-- A = items making up the first 80% of revenue, B = next 15%, C = last 5%.
-- The share BEFORE each item is used so the item crossing the 80% line stays an A.
-- Items are ranked by revenue summed over all stores and all weeks (ties broken by item_id so the result is repeatable).
-- =====================================================================

-- name: abc_classification
WITH rev AS (
    SELECT i.item_id, i.cat_id, SUM(f.revenue) AS revenue
    FROM fact_weekly_sales f JOIN dim_item i USING (item_key)
    GROUP BY i.item_id, i.cat_id
),
cum AS (
    SELECT item_id, cat_id, revenue,
           SUM(revenue) OVER (ORDER BY revenue DESC, item_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_revenue,
           SUM(revenue) OVER ()                                                                             AS total_revenue
    FROM rev
)
SELECT item_id, cat_id AS category, ROUND(revenue, 2) AS revenue,
       ROUND(100.0 * revenue / total_revenue, 4)     AS revenue_pct,
       ROUND(100.0 * cum_revenue / total_revenue, 2) AS cumulative_pct,
       CASE WHEN (cum_revenue - revenue) / total_revenue < 0.80 THEN 'A'
            WHEN (cum_revenue - revenue) / total_revenue < 0.95 THEN 'B'
            ELSE 'C' END AS abc_class
FROM cum
ORDER BY revenue DESC, item_id;

-- name: abc_summary
WITH rev AS (
    SELECT item_key, SUM(revenue) AS revenue, SUM(units) AS units FROM fact_weekly_sales GROUP BY item_key
),
cls AS (
    SELECT item_key, revenue, units,
           CASE WHEN (SUM(revenue) OVER (ORDER BY revenue DESC, item_key ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) - revenue)
                     / SUM(revenue) OVER () < 0.80 THEN 'A'
                WHEN (SUM(revenue) OVER (ORDER BY revenue DESC, item_key ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) - revenue)
                     / SUM(revenue) OVER () < 0.95 THEN 'B'
                ELSE 'C' END AS abc_class
    FROM rev
)
SELECT abc_class, COUNT(*) AS n_items,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)      AS items_pct,
       ROUND(SUM(revenue), 2)                                  AS revenue,
       ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 1) AS revenue_pct,
       ROUND(SUM(revenue) / SUM(units), 3)                     AS avg_selling_price
FROM cls GROUP BY abc_class ORDER BY abc_class;

-- name: abc_by_category
WITH rev AS (
    SELECT i.item_key, i.cat_id, SUM(f.revenue) AS revenue
    FROM fact_weekly_sales f JOIN dim_item i USING (item_key) GROUP BY i.item_key, i.cat_id
),
cls AS (
    SELECT item_key, cat_id, revenue,
           CASE WHEN (SUM(revenue) OVER (ORDER BY revenue DESC, item_key ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) - revenue)
                     / SUM(revenue) OVER () < 0.80 THEN 'A'
                WHEN (SUM(revenue) OVER (ORDER BY revenue DESC, item_key ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) - revenue)
                     / SUM(revenue) OVER () < 0.95 THEN 'B'
                ELSE 'C' END AS abc_class
    FROM rev
)
SELECT cat_id AS category, abc_class, COUNT(*) AS n_items, ROUND(SUM(revenue), 2) AS revenue,
       ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (PARTITION BY cat_id), 1) AS share_of_category_revenue_pct
FROM cls GROUP BY cat_id, abc_class ORDER BY cat_id, abc_class;
