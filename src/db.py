"""
db.py - build the SQLite database and run the named SQL queries.

SQLite ships with Python (module `sqlite3`) - no server, no Docker, nothing to install.
"""
import re
import sqlite3

import pandas as pd

import config as cfg


def build_database(tables, db_path=cfg.DB_PATH, schema_path=cfg.SQL_DIR / "00_schema.sql"):
    """Create the schema from sql/00_schema.sql and load the cleaned tables. Returns the db path."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()                       # always rebuild from scratch -> reproducible
    con = sqlite3.connect(db_path)
    try:
        con.executescript(schema_path.read_text(encoding="utf-8"))
        order = ["warehouses", "suppliers", "products", "demand_daily", "inventory_daily",
                 "inventory_policy", "purchase_orders"]           # parents before children (foreign keys)
        for name in order:
            df = tables[name].copy()
            for c in df.columns:               # dates -> ISO text
                if pd.api.types.is_datetime64_any_dtype(df[c]):
                    df[c] = df[c].dt.strftime("%Y-%m-%d")
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({name})")]
            df[cols].to_sql(name, con, if_exists="append", index=False, chunksize=20000)
        con.commit()
    finally:
        con.close()
    return db_path


def parse_named_queries(sql_text):
    """Split a .sql file into {query_name: sql} using the '-- name: xxx' markers."""
    parts = re.split(r"^--\s*name:\s*(\w+)\s*$", sql_text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def run_query(sql, db_path=cfg.DB_PATH):
    con = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query(sql, con)
    finally:
        con.close()


def run_all_sql_files(db_path=cfg.DB_PATH, out_dir=cfg.SQL_RESULTS):
    """Run every query in sql/01..06 and save results as CSV. Returns {file__query: DataFrame}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for f in sorted(cfg.SQL_DIR.glob("0[1-9]_*.sql")):
        for name, sql in parse_named_queries(f.read_text(encoding="utf-8")).items():
            df = run_query(sql, db_path)
            key = f"{f.stem}__{name}"
            df.to_csv(out_dir / f"{key}.csv", index=False)
            results[key] = df
    return results
