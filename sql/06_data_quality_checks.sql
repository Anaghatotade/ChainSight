-- =====================================================================
-- 06  Data-quality / integrity checks on the loaded database (every "issues" value should be 0)
-- =====================================================================

-- name: dq_table_counts
SELECT 'dim_item' AS table_name, COUNT(*) AS n_rows FROM dim_item
UNION ALL SELECT 'dim_store', COUNT(*) FROM dim_store
UNION ALL SELECT 'dim_week', COUNT(*) FROM dim_week
UNION ALL SELECT 'dim_date', COUNT(*) FROM dim_date
UNION ALL SELECT 'fact_weekly_sales', COUNT(*) FROM fact_weekly_sales
UNION ALL SELECT 'fact_daily_sales', COUNT(*) FROM fact_daily_sales;

-- name: dq_integrity_checks
SELECT 'weekly fact: orphan item' AS check_name, COUNT(*) AS issues
FROM fact_weekly_sales f LEFT JOIN dim_item i USING (item_key) WHERE i.item_key IS NULL
UNION ALL SELECT 'weekly fact: orphan store', COUNT(*)
FROM fact_weekly_sales f LEFT JOIN dim_store s USING (store_key) WHERE s.store_key IS NULL
UNION ALL SELECT 'weekly fact: orphan week', COUNT(*)
FROM fact_weekly_sales f LEFT JOIN dim_week w USING (week_idx) WHERE w.week_idx IS NULL
UNION ALL SELECT 'daily fact: orphan date', COUNT(*)
FROM fact_daily_sales f LEFT JOIN dim_date d USING (date) WHERE d.date IS NULL
UNION ALL SELECT 'daily fact: orphan store', COUNT(*)
FROM fact_daily_sales f LEFT JOIN dim_store s USING (store_key) WHERE s.store_key IS NULL
UNION ALL SELECT 'negative units', COUNT(*) FROM fact_weekly_sales WHERE units < 0
UNION ALL SELECT 'non-positive price', COUNT(*) FROM fact_weekly_sales WHERE sell_price <= 0
UNION ALL SELECT 'revenue differs from units x price', COUNT(*) FROM fact_weekly_sales WHERE ABS(revenue - units * sell_price) > 0.011
UNION ALL SELECT 'week index not contiguous', (SELECT CASE WHEN MAX(week_idx) - MIN(week_idx) + 1 = COUNT(*) THEN 0 ELSE 1 END FROM dim_week)
UNION ALL SELECT 'department does not belong to its category', COUNT(*) FROM dim_item WHERE dept_id NOT LIKE cat_id || '\_%' ESCAPE '\'
UNION ALL SELECT 'weekly vs daily units differ (total)',
       (SELECT CASE WHEN (SELECT SUM(units) FROM fact_weekly_sales) = (SELECT SUM(units) FROM fact_daily_sales) THEN 0 ELSE 1 END);
