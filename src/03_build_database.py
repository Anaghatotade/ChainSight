"""
Step 3 - load the cleaned data into a SQLite database.

Reads  data/processed/panel.npz, series.csv, weeks.csv, daily_store_dept.csv, dim_date.csv   and   sql/00_schema.sql
Writes data/processed/m5_retail.db   (a few hundred MB - rebuilt every time, not committed to git)

Run:  python src/03_build_database.py          (about 1-2 minutes)
"""
import sqlite3

import pandas as pd

import config as cfg
import db
import panel as pn


def main():
    panel = pn.load_panel()
    daily = pd.read_csv(cfg.DATA_PROCESSED / "daily_store_dept.csv")
    dim_date = pd.read_csv(cfg.DATA_PROCESSED / "dim_date.csv")
    path = db.build_database(panel, daily, dim_date)
    con = sqlite3.connect(path)
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        n = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"{name:<20} {n:>10,} rows")
    con.close()
    print(f"Database created: {path}  ({path.stat().st_size / 1e6:,.0f} MB)")


if __name__ == "__main__":
    main()
