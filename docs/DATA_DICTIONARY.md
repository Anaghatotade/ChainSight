# Data dictionary

Raw files live in `data/raw/` (messy), cleaned files in `data/processed/`. Dates are ISO `YYYY-MM-DD` after cleaning.

## demand_daily  (grain: sku x warehouse_code x date)
| Column | Meaning |
|---|---|
| sku, warehouse_code, date | business key (unique after cleaning) |
| units_demanded | customer demand that day (units) |
| units_fulfilled | units actually shipped (<= demanded) |
| promo_flag | 1 if the SKU had a promotion that day |
| stockout_flag | *(derived in cleaning)* 1 if fulfilled < demanded |

## inventory_daily  (grain: sku x warehouse_code x date)
`on_hand_units` (end-of-day stock), `in_transit_units` (ordered, not yet received).

## inventory_policy  (one row per sku x warehouse)
Current policy: `reorder_point_units`, `safety_stock_units`, `order_up_to_units`, `review_period_days`, `policy_set_date`.

## purchase_orders  (one row per PO)
`po_number`, `supplier_code`, `sku`, `warehouse_code`, `order_date`, `promised_delivery_date`, `actual_delivery_date` (blank = still open or invalid), `quantity`, `unit_cost`, `ship_mode` (air/road/rail/ocean), `freight_cost`, `status`.
Derived in cleaning: `delivery_date_invalid`, `po_value`, `promised_lead_days`, `actual_lead_days`, `delay_days`, `on_time_flag`.

## products / suppliers / warehouses
`products`: sku, product_name, category, sub_category, unit_cost, unit_price, supplier_code.
`suppliers`: supplier_code, supplier_name, country, region, category, quoted_lead_time_days.
`warehouses`: warehouse_code, warehouse_name, region, capacity_units.

## Injected data-quality problems (raw layer only)
Duplicate rows; SKU/warehouse codes in lowercase or with trailing spaces; dates as `dd-Mon-yyyy`; missing demand / stock / unit cost / freight / quoted lead time; negative demand, stock and PO quantity; fulfilled > demanded; demand typos (x100); deliveries dated before the order; category/region text variants; ship-mode case. Each fix is logged in `outputs/tables/cleaning_log.csv`.

## Outputs worth knowing
| File | Content |
|---|---|
| outputs/tables/key_numbers.json | every number quoted in README / INTERVIEW_NOTES |
| outputs/tables/kpi_sku.csv | master KPI table, one row per SKU |
| outputs/tables/kpi_policy_check.csv | current vs recommended reorder policy per SKU-warehouse |
| outputs/tables/forecast_model_comparison.csv | WAPE / RMSE / bias per model and split |
| outputs/tables/error_analysis_top100.csv | the 100 largest dev errors with cause tags (+ empty manual columns) |
| outputs/dashboard/*.csv, ChainSight_Dashboard_Data.xlsx | Power BI / Excel ready tables |
| outputs/sql_results/*.csv | result of every SQL query in `sql/` |
