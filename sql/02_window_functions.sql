-- =====================================================================
-- 02  Window-function queries (LAG, moving average, ROW_NUMBER, RANK, running totals, gaps-and-islands)
-- =====================================================================

-- name: weekly_revenue_wow_growth
-- Weekly company revenue, week-over-week growth (LAG), 4-week and 52-week moving averages.
WITH weekly AS (
    SELECT week_idx, SUM(units) AS units, SUM(revenue) AS revenue FROM fact_weekly_sales GROUP BY week_idx
)
SELECT w.week_start, weekly.units, ROUND(weekly.revenue, 2) AS revenue,
       ROUND(100.0 * (weekly.revenue - LAG(weekly.revenue) OVER (ORDER BY weekly.week_idx))
             / LAG(weekly.revenue) OVER (ORDER BY weekly.week_idx), 2)                       AS wow_growth_pct,
       ROUND(AVG(weekly.revenue) OVER (ORDER BY weekly.week_idx ROWS BETWEEN 3 PRECEDING AND CURRENT ROW), 2) AS moving_avg_4w,
       CASE WHEN weekly.week_idx >= 51
            THEN ROUND(AVG(weekly.revenue) OVER (ORDER BY weekly.week_idx ROWS BETWEEN 51 PRECEDING AND CURRENT ROW), 2) END AS moving_avg_52w
FROM weekly JOIN dim_week w USING (week_idx)
ORDER BY weekly.week_idx;

-- name: monthly_category_mom_yoy
-- Revenue per week by category and month, with month-over-month (LAG 1) and year-over-year (LAG 12) growth.
WITH cat_week AS (
    SELECT i.cat_id, f.week_idx, SUM(f.revenue) AS revenue
    FROM fact_weekly_sales f JOIN dim_item i USING (item_key) GROUP BY i.cat_id, f.week_idx
),
cat_month AS (
    SELECT c.cat_id, w.year, w.month, COUNT(*) AS n_weeks, SUM(c.revenue) / COUNT(*) AS revenue_per_week
    FROM cat_week c JOIN dim_week w USING (week_idx) GROUP BY c.cat_id, w.year, w.month
)
SELECT cat_id AS category, year, month, n_weeks, ROUND(revenue_per_week, 2) AS revenue_per_week,
       ROUND(100.0 * (revenue_per_week / LAG(revenue_per_week, 1)  OVER (PARTITION BY cat_id ORDER BY year, month) - 1), 2) AS mom_growth_pct,
       ROUND(100.0 * (revenue_per_week / LAG(revenue_per_week, 12) OVER (PARTITION BY cat_id ORDER BY year, month) - 1), 2) AS yoy_growth_pct
FROM cat_month
ORDER BY cat_id, year, month;

-- name: running_revenue_by_year_category
-- Running total inside each category-year (SUM OVER with PARTITION BY + ORDER BY).
WITH cat_week AS (
    SELECT i.cat_id, f.week_idx, SUM(f.revenue) AS revenue
    FROM fact_weekly_sales f JOIN dim_item i USING (item_key) GROUP BY i.cat_id, f.week_idx
),
cat_month AS (
    SELECT c.cat_id, w.year, w.month, SUM(c.revenue) AS revenue
    FROM cat_week c JOIN dim_week w USING (week_idx) GROUP BY c.cat_id, w.year, w.month
)
SELECT cat_id AS category, year, month, ROUND(revenue, 2) AS revenue,
       ROUND(SUM(revenue) OVER (PARTITION BY cat_id, year ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS running_revenue_in_year
FROM cat_month
WHERE year IN (2013, 2014, 2015)
ORDER BY cat_id, year, month;

-- name: top3_items_per_department
-- ROW_NUMBER() inside each department: the 3 biggest revenue items + their share of the department.
WITH item_rev AS (
    SELECT i.dept_id, i.item_id, SUM(f.revenue) AS revenue
    FROM fact_weekly_sales f JOIN dim_item i USING (item_key) GROUP BY i.dept_id, i.item_id
),
ranked AS (
    SELECT dept_id, item_id, revenue,
           ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY revenue DESC, item_id) AS rank_in_dept,
           revenue / SUM(revenue) OVER (PARTITION BY dept_id)                      AS share_of_dept
    FROM item_rev
)
SELECT dept_id AS department, rank_in_dept, item_id, ROUND(revenue, 2) AS revenue, ROUND(100.0 * share_of_dept, 2) AS share_of_dept_pct
FROM ranked WHERE rank_in_dept <= 3
ORDER BY dept_id, rank_in_dept;

-- name: store_rank_within_state
-- RANK() of stores inside their state + gap to the state leader.
WITH st AS (
    SELECT s.store_id, s.state_id, SUM(f.revenue) AS revenue
    FROM fact_weekly_sales f JOIN dim_store s USING (store_key) GROUP BY s.store_id, s.state_id
)
SELECT state_id, store_id, ROUND(revenue, 2) AS revenue,
       RANK() OVER (PARTITION BY state_id ORDER BY revenue DESC) AS rank_in_state,
       ROUND(100.0 * (revenue / MAX(revenue) OVER (PARTITION BY state_id) - 1), 1) AS gap_to_state_leader_pct
FROM st
ORDER BY state_id, rank_in_state;

-- name: longest_zero_sales_streaks_ca1
-- Gaps-and-islands: consecutive on-sale weeks with ZERO units in store CA_1 (week_idx minus ROW_NUMBER is constant inside a streak).
-- Zero weeks are common for slow items; very long streaks are candidates for range review.
WITH z AS (
    SELECT f.item_key, f.week_idx,
           f.week_idx - ROW_NUMBER() OVER (PARTITION BY f.item_key ORDER BY f.week_idx) AS grp
    FROM fact_weekly_sales f JOIN dim_store s USING (store_key)
    WHERE s.store_id = 'CA_1' AND f.units = 0
)
SELECT i.item_id, MIN(z.week_idx) AS first_week, MAX(z.week_idx) AS last_week, COUNT(*) AS streak_weeks
FROM z JOIN dim_item i USING (item_key)
GROUP BY z.item_key, z.grp
ORDER BY streak_weeks DESC, i.item_id
LIMIT 20;
