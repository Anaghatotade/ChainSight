-- =====================================================================
-- 04  Stockout analysis
-- =====================================================================

-- name: top15_skus_by_lost_revenue
SELECT d.sku, p.category,
       SUM(d.units_demanded - d.units_fulfilled)                            AS lost_units,
       ROUND(SUM((d.units_demanded - d.units_fulfilled) * p.unit_price), 0)  AS lost_revenue,
       ROUND(100.0 * AVG(d.stockout_flag), 1)                               AS stockout_day_pct,
       ROUND(100.0 * SUM(d.units_fulfilled) / SUM(d.units_demanded), 1)     AS fill_rate_pct
FROM demand_daily d JOIN products p ON p.sku = d.sku
GROUP BY d.sku, p.category
ORDER BY lost_revenue DESC
LIMIT 15;

-- name: stockout_promo_vs_normal
-- Do promotions cause stockouts? Compare stockout rate on promo vs non-promo days.
SELECT CASE promo_flag WHEN 1 THEN 'promo day' ELSE 'normal day' END AS day_type,
       COUNT(*)                                                       AS sku_warehouse_days,
       ROUND(100.0 * AVG(stockout_flag), 2)                           AS stockout_rate_pct,
       ROUND(100.0 * SUM(units_fulfilled) / SUM(units_demanded), 2)   AS fill_rate_pct
FROM demand_daily
GROUP BY promo_flag;

-- name: stockout_by_category_and_quarter
SELECT p.category,
       substr(d.date, 1, 4) || '-Q' || ((CAST(substr(d.date, 6, 2) AS INTEGER) + 2) / 3) AS quarter,
       ROUND(100.0 * AVG(d.stockout_flag), 2)                                           AS stockout_rate_pct
FROM demand_daily d JOIN products p ON p.sku = d.sku
GROUP BY p.category, quarter
ORDER BY p.category, quarter;

-- name: longest_stockout_streaks
-- "Gaps and islands": consecutive stockout days per SKU-warehouse. The trick: for stockout rows,
-- (row number over ALL days) - (row number over stockout days) is constant inside one streak.
WITH numbered AS (
    SELECT sku, warehouse_code, date, stockout_flag,
           ROW_NUMBER() OVER (PARTITION BY sku, warehouse_code ORDER BY date) AS rn_all
    FROM demand_daily
),
so AS (
    SELECT *, rn_all - ROW_NUMBER() OVER (PARTITION BY sku, warehouse_code ORDER BY date) AS grp
    FROM numbered WHERE stockout_flag = 1
)
SELECT sku, warehouse_code, MIN(date) AS streak_start, MAX(date) AS streak_end, COUNT(*) AS streak_days
FROM so
GROUP BY sku, warehouse_code, grp
ORDER BY streak_days DESC, sku
LIMIT 20;

-- name: stockout_vs_current_policy
-- Join the demand rows with the current policy: stockout rate in the LAST 13 weeks for SKU-warehouses
-- whose CURRENT reorder point covers less than 'lead-time demand', i.e. avg recent daily demand x quoted lead time.
WITH recent AS (
    SELECT sku, warehouse_code, AVG(units_demanded) AS recent_avg_demand, AVG(stockout_flag) AS recent_stockout_rate
    FROM demand_daily
    WHERE date > date((SELECT MAX(date) FROM demand_daily), '-91 days')
    GROUP BY sku, warehouse_code
)
SELECT CASE WHEN pol.reorder_point_units < r.recent_avg_demand * s.quoted_lead_time_days
            THEN 'ROP below recent lead-time demand' ELSE 'ROP covers lead-time demand' END AS policy_status,
       COUNT(*)                                       AS n_sku_warehouses,
       ROUND(100.0 * AVG(r.recent_stockout_rate), 2)  AS recent_stockout_rate_pct
FROM recent r
JOIN inventory_policy pol ON pol.sku = r.sku AND pol.warehouse_code = r.warehouse_code
JOIN products   p ON p.sku = r.sku
JOIN suppliers  s ON s.supplier_code = p.supplier_code
GROUP BY policy_status;
