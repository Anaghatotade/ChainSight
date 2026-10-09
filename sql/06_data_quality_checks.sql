-- =====================================================================
-- 06  Data-quality checks on the loaded database (every 'issues' value should be 0)
-- =====================================================================

-- name: dq_row_counts
SELECT 'demand_daily' AS table_name, COUNT(*) AS n_rows FROM demand_daily
UNION ALL SELECT 'inventory_daily', COUNT(*) FROM inventory_daily
UNION ALL SELECT 'purchase_orders', COUNT(*) FROM purchase_orders
UNION ALL SELECT 'products', COUNT(*) FROM products
UNION ALL SELECT 'suppliers', COUNT(*) FROM suppliers;

-- name: dq_integrity_checks
SELECT 'demand rows without a product (LEFT JOIN orphan)' AS check_name, COUNT(*) AS issues
FROM demand_daily d LEFT JOIN products p ON p.sku = d.sku WHERE p.sku IS NULL
UNION ALL
SELECT 'POs without a supplier', COUNT(*)
FROM purchase_orders po LEFT JOIN suppliers s ON s.supplier_code = po.supplier_code WHERE s.supplier_code IS NULL
UNION ALL
SELECT 'fulfilled > demanded', COUNT(*) FROM demand_daily WHERE units_fulfilled > units_demanded
UNION ALL
SELECT 'negative on-hand stock', COUNT(*) FROM inventory_daily WHERE on_hand_units < 0
UNION ALL
SELECT 'delivery before order date', COUNT(*) FROM purchase_orders WHERE actual_delivery_date < order_date
UNION ALL
SELECT 'demand SKU-warehouse-days missing vs inventory table', COUNT(*)
FROM inventory_daily i LEFT JOIN demand_daily d
     ON d.sku = i.sku AND d.warehouse_code = i.warehouse_code AND d.date = i.date
WHERE d.sku IS NULL;
