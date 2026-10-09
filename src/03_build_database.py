"""
Step 3 - load the cleaned CSVs into a SQLite database.

Reads  data/processed/*.csv   and   sql/00_schema.sql
Writes data/processed/chainsight.db

Run:  python src/03_build_database.py
"""
import sqlite3

import config as cfg
import db
import kpis


def main():
    tables = kpis.load_clean()
    path = db.build_database(tables)
    con = sqlite3.connect(path)
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        n = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"{name:<18} {n:>9,} rows")
    con.close()
    print("Database created:", path)


if __name__ == "__main__":
    main()
