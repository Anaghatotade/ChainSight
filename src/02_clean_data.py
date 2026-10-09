"""
Step 2 - clean the raw data.

Reads  data/raw/*.csv
Writes data/processed/*.csv, outputs/tables/cleaning_log.csv, outputs/tables/data_quality_summary.csv

Run:  python src/02_clean_data.py
"""
import pandas as pd

import cleaning
import config as cfg
import keynums


def main():
    cfg.ensure_dirs()
    raw = {p.stem: pd.read_csv(p) for p in sorted(cfg.DATA_RAW.glob("*.csv"))}
    clean, log = cleaning.clean_all(raw)
    for name, df in clean.items():
        df.to_csv(cfg.DATA_PROCESSED / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    log.to_csv(cfg.TABLES / "cleaning_log.csv", index=False)
    summary = cleaning.data_quality_summary(raw, clean)
    summary.to_csv(cfg.TABLES / "data_quality_summary.csv", index=False)
    keynums.save({f"dq_rows_raw_{r.table}": r.rows_raw for r in summary.itertuples()})
    print(log.to_string(index=False))
    print()
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
