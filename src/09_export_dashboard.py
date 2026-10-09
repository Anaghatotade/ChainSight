"""
Step 9 - export dashboard-ready files for Power BI / Excel / Tableau.

Writes into outputs/dashboard/:
  * CSV star schema: dim_product, dim_supplier, dim_warehouse, dim_date, fact_demand_weekly,
    fact_purchase_orders, plus the KPI and forecast tables
  * ChainSight_Dashboard_Data.xlsx - the same tables as formatted sheets (one workbook to open in Excel)
The PNG charts in outputs/charts/ can be dropped straight into PowerPoint / Power BI as images.

Power BI tip: Get Data -> Text/CSV -> pick these files; relate fact tables to dims on sku / supplier_code /
warehouse_code / week_start. Daily-level facts (131k rows) are in data/processed/ if you need them.

Run:  python src/09_export_dashboard.py
"""
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import config as cfg
import kpis

PCT_HINTS = ("rate", "share", "wape", "bias", "pct", "gap_pct", "cv", "on_time")
MONEY_HINTS = ("revenue", "value", "cost", "invest")


def main():
    cfg.ensure_dirs()
    t = kpis.load_clean()
    T = cfg.TABLES
    weekly = kpis.weekly_demand(t)
    sku = pd.read_csv(T / "kpi_sku.csv")

    # ------------------------------------------------------------ star schema CSVs
    dim_product = t["products"].merge(sku[["sku", "abc_class", "cv_band", "demand_cv"]], on="sku", how="left")
    all_days = pd.date_range(t["demand_daily"]["date"].min(), t["demand_daily"]["date"].max(), freq="D")
    dim_date = pd.DataFrame({"date": all_days})
    dim_date["week_start"] = dim_date["date"] - pd.to_timedelta(dim_date["date"].dt.weekday, unit="D")
    dim_date["month"] = dim_date["date"].dt.to_period("M").dt.to_timestamp()
    dim_date["year"], dim_date["month_number"] = dim_date["date"].dt.year, dim_date["date"].dt.month
    dim_date["quarter"] = "Q" + dim_date["date"].dt.quarter.astype(str)
    prices = t["products"].set_index("sku")[["unit_price", "unit_cost"]]
    fact_w = weekly.copy()
    fact_w["revenue"] = fact_w["units_fulfilled"] * fact_w["sku"].map(prices["unit_price"])
    fact_w["lost_revenue"] = (fact_w["units_demanded"] - fact_w["units_fulfilled"]) * fact_w["sku"].map(prices["unit_price"])
    fact_w = fact_w[["sku", "week_idx", "week_start", "units_demanded", "units_fulfilled", "revenue", "lost_revenue", "promo_flag", "promo_days_n"]]

    csvs = {"dim_product": dim_product, "dim_supplier": t["suppliers"], "dim_warehouse": t["warehouses"], "dim_date": dim_date,
            "fact_demand_weekly": fact_w, "fact_purchase_orders": t["purchase_orders"]}
    for src in ["kpi_overall", "kpi_sku", "kpi_category", "kpi_warehouse", "kpi_region", "kpi_monthly", "kpi_abc_summary",
                "kpi_lead_time_supplier", "kpi_lead_time_mode", "kpi_policy_check", "forecast_model_comparison",
                "forecast_predictions", "error_analysis_top100", "error_analysis_tally", "recommendations", "cleaning_log"]:
        csvs[src] = pd.read_csv(T / f"{src}.csv")
    for name, df in csvs.items():
        df.to_csv(cfg.DASHBOARD / f"{name}.csv", index=False, date_format="%Y-%m-%d")

    # ------------------------------------------------------------ Excel workbook
    overall = csvs["kpi_overall"].iloc[0]
    definitions = {
        "fill_rate": "Units fulfilled / units demanded", "stockout_rate": "Share of SKU-warehouse-days where demand was not fully met",
        "inventory_turnover": "Annualised COGS / average inventory value", "days_of_inventory": "Average units on hand / average daily units sold",
        "revenue": "Fulfilled units x unit price", "lost_revenue": "Unfulfilled units x unit price",
        "avg_inventory_value": "Average daily inventory valued at unit cost", "units_demanded": "Total units demanded",
        "n_skus": "Number of SKUs", "n_days": "Days of history"}
    kpi_summary = pd.DataFrame({"kpi": list(definitions), "value": [overall[k] for k in definitions], "definition": list(definitions.values())})
    sheets = {
        "KPI_Summary": kpi_summary, "KPI_by_SKU": csvs["kpi_sku"], "KPI_by_Category": csvs["kpi_category"],
        "KPI_by_Warehouse": csvs["kpi_warehouse"], "KPI_Monthly": csvs["kpi_monthly"], "ABC_Summary": csvs["kpi_abc_summary"],
        "Lead_Time_Supplier": csvs["kpi_lead_time_supplier"], "Lead_Time_Mode": csvs["kpi_lead_time_mode"],
        "Policy_Check": csvs["kpi_policy_check"], "Weekly_Demand": fact_w, "Forecast_Comparison": csvs["forecast_model_comparison"],
        "Forecast_Predictions": csvs["forecast_predictions"], "Error_Top100": csvs["error_analysis_top100"],
        "Error_Tally": csvs["error_analysis_tally"], "Recommendations": csvs["recommendations"], "Cleaning_Log": csvs["cleaning_log"]}
    readme = pd.DataFrame({"sheet": ["README"] + list(sheets), "what_it_contains": ["This page"] + [
        "Headline KPIs with definitions", "One row per SKU: fill rate, turnover, days of inventory, CV, ABC", "KPIs by product category",
        "KPIs by warehouse", "KPIs by month (trend)", "What A / B / C items contribute", "Supplier on-time and lead-time statistics",
        "Lead time and freight by shipping mode", "Current reorder policy vs recommended (per SKU-warehouse)", "Weekly demand per SKU (forecasting input)",
        "Baselines vs linear vs MLP: WAPE, RMSE, bias", "Weekly forecasts per model (dev + test)", "100 largest dev-set errors with cause tags (fill manual_cause!)",
        "Count of the top errors by primary cause", "Business recommendations", "Every cleaning rule and rows affected"]})
    path = cfg.DASHBOARD / "ChainSight_Dashboard_Data.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl", datetime_format="yyyy-mm-dd") as xw:
        readme.to_excel(xw, sheet_name="README", index=False)       # sheet_name as keyword: works in pandas 2 and 3
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
        header_fill = PatternFill("solid", fgColor="1F4E79")
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
                cell.fill = header_fill
                cell.alignment = Alignment(wrap_text=True, vertical="center")
            for ci, col in enumerate(ws.iter_cols(min_row=1, max_row=min(ws.max_row, 200)), start=1):
                name = str(col[0].value or "").lower()
                width = min(60, max(10, max(len(str(c.value)) if c.value is not None else 0 for c in col[:60]) + 2))
                if name in ("finding", "action", "what_it_contains", "definition", "rule", "issue"):
                    width = 70
                ws.column_dimensions[get_column_letter(ci)].width = width
                fmt = None
                if any(h in name for h in PCT_HINTS) and not any(h in name for h in ("revenue", "value", "cost")):
                    fmt = "0.0%"
                elif any(h in name for h in MONEY_HINTS):
                    fmt = "#,##0"
                for c in col[1:]:
                    c.font = Font(name="Arial", size=10)
                    if fmt and isinstance(c.value, (int, float)):
                        c.number_format = fmt
    # KPI_Summary mixes units: format each row by its own meaning
    wb = load_workbook(path)
    for row in wb["KPI_Summary"].iter_rows(min_row=2):
        row[1].number_format = {"fill_rate": "0.0%", "stockout_rate": "0.0%", "inventory_turnover": "0.0",
                                "days_of_inventory": "0.0"}.get(row[0].value, "#,##0")
    wb.save(path)
    print("Wrote", path)
    for p in sorted(cfg.DASHBOARD.glob("*.csv")):
        print(" ", p.name)


if __name__ == "__main__":
    main()
