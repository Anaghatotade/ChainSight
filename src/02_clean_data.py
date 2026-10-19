"""
Step 2 - validate / clean the raw M5 data and build the weekly panel.

Reads  data/raw/{calendar, sales_train_validation, sell_prices}
Writes data/processed/panel.npz, series.csv, weeks.csv, daily_store_dept.csv, dim_date.csv
       outputs/tables/cleaning_log.csv, data_quality_summary.csv, key_numbers.json (dq_* keys)

Run:  python src/02_clean_data.py          (about 1 minute)
"""
import pandas as pd

import config as cfg
import cleaning
import keynums
import panel as pn


def main():
    cfg.ensure_dirs()
    raw = pn.load_raw()
    panel, daily, dim_date, log = cleaning.clean_all(raw)
    pn.save_panel(panel)
    daily.to_csv(cfg.DATA_PROCESSED / "daily_store_dept.csv", index=False)
    dim_date.to_csv(cfg.DATA_PROCESSED / "dim_date.csv", index=False)
    log.to_csv(cfg.TABLES / "cleaning_log.csv", index=False)
    summary = cleaning.data_quality_summary(raw, panel, daily)
    summary.to_csv(cfg.TABLES / "data_quality_summary.csv", index=False)

    L = log.set_index("rule")["rows_affected"]
    on = panel.onsale
    keynums.save({
        "data_n_series": panel.n_series, "data_n_items": panel.series["item_id"].nunique(),
        "data_n_stores": panel.series["store_id"].nunique(), "data_n_states": panel.series["state_id"].nunique(),
        "data_n_depts": panel.series["dept_id"].nunique(), "data_n_categories": panel.series["cat_id"].nunique(),
        "data_n_weeks": panel.n_weeks, "data_n_days": panel.n_weeks * 7,
        "data_start_date": str(panel.weeks["week_start"].min().date()),
        "data_end_date": str((panel.weeks["week_start"].max() + pd.Timedelta(days=6)).date()),
        "data_n_sales_rows_raw": len(raw["sales"]), "data_n_price_rows_raw": len(raw["prices"]),
        "data_total_units": int(panel.units.sum()), "data_total_revenue": float(panel.revenue().sum()),
        "dq_not_on_sale_series_weeks": int((~on).sum()), "dq_not_on_sale_share": float((~on).mean()),
        "dq_on_sale_series_weeks": int(on.sum()),
        "dq_delisted_series": int(L[[r for r in L.index if r.startswith("delisted")][0]]),
        "dq_price_jumps": int(L[[r for r in L.index if "price change by more" in r][0]]),
        "dq_spike_weeks": int(L[[r for r in L.index if "above" in r and "median" in r][0]]),
        "dq_units_without_price": int(L["sales recorded in a week with no price"]),
        "dq_dropped_days": len([c for c in raw["sales"].columns if c.startswith("d_")]) - panel.n_weeks * 7,
    })
    print(log.to_string(index=False))
    print()
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
