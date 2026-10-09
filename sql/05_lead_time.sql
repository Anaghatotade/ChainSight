-- =====================================================================
-- 05  Lead-time & supplier performance (delivered POs with a valid delivery date only)
-- =====================================================================

-- name: supplier_scorecard
SELECT po.supplier_code, s.supplier_name, s.region,
       COUNT(*)                                          AS n_pos,
       ROUND(AVG(po.promised_lead_days), 1)              AS avg_promised_days,
       ROUND(AVG(po.actual_lead_days), 1)                AS avg_actual_days,
       ROUND(100.0 * AVG(po.on_time_flag), 1)            AS on_time_pct,
       ROUND(AVG(CASE WHEN po.delay_days > 0 THEN po.delay_days END), 1) AS avg_delay_when_late,
       RANK() OVER (ORDER BY AVG(po.on_time_flag) DESC)  AS on_time_rank
FROM purchase_orders po
JOIN suppliers s ON s.supplier_code = po.supplier_code
WHERE po.actual_lead_days IS NOT NULL
GROUP BY po.supplier_code, s.supplier_name, s.region
ORDER BY on_time_rank;

-- name: ship_mode_comparison
SELECT ship_mode,
       COUNT(*)                                            AS n_pos,
       ROUND(AVG(actual_lead_days), 1)                     AS avg_lead_days,
       ROUND(100.0 * AVG(on_time_flag), 1)                 AS on_time_pct,
       ROUND(100.0 * SUM(freight_cost) / SUM(po_value), 2) AS freight_pct_of_value
FROM purchase_orders
WHERE actual_lead_days IS NOT NULL
GROUP BY ship_mode ORDER BY avg_lead_days;

-- name: lead_time_by_supplier_region
SELECT s.region AS supplier_region,
       COUNT(*)                          AS n_pos,
       ROUND(AVG(po.actual_lead_days),1) AS avg_lead_days,
       ROUND(AVG(po.delay_days), 2)      AS avg_delay_days
FROM purchase_orders po JOIN suppliers s ON s.supplier_code = po.supplier_code
WHERE po.actual_lead_days IS NOT NULL
GROUP BY s.region ORDER BY avg_lead_days DESC;

-- name: emergency_air_freight_premium
-- How much extra freight do we pay by expediting? (air vs everything else, as % of goods value)
SELECT CASE WHEN ship_mode = 'air' THEN 'air' ELSE 'non-air' END AS freight_type,
       COUNT(*)                                               AS n_pos,
       ROUND(SUM(freight_cost), 0)                            AS freight_cost,
       ROUND(100.0 * SUM(freight_cost) / SUM(po_value), 2)    AS freight_pct_of_value
FROM purchase_orders GROUP BY freight_type;
