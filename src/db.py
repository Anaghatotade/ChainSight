"""
db.py - build the SQLite database and run the named SQL queries.

SQLite ships with Python (module `sqlite3`) - no server, no Docker, nothing to install.
The fact table holds one row per item x store x week in which the item was on sale (about 6.6 million rows for the
full M5 data), so the .db file is a few hundred MB: it is rebuilt by step 03 and is NOT committed to git.
"""
import re
import sqlite3

import numpy as np
import pandas as pd

import config as cfg

CHUNK = 400_000


def _insert(con, sql, rows):
    con.executemany(sql, rows)


def build_database(panel, daily, dim_date, db_path=None, schema_path=None):
    """Create the schema from sql/00_schema.sql and load the cleaned panel. Returns the db path."""
    db_path = db_path or cfg.DB_PATH
    schema_path = schema_path or cfg.SQL_DIR / "00_schema.sql"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()                       # always rebuild from scratch -> reproducible
    con = sqlite3.connect(db_path)
    try:
        con.executescript(schema_path.read_text(encoding="utf-8"))
        con.execute("PRAGMA journal_mode = OFF")
        con.execute("PRAGMA synchronous = OFF")

        # ---- dimensions
        s = panel.series
        items = s.drop_duplicates("item_id")[["item_id", "dept_id", "cat_id"]].sort_values("item_id").reset_index(drop=True)
        stores = s.drop_duplicates("store_id")[["store_id", "state_id"]].sort_values("store_id").reset_index(drop=True)
        items["item_key"], stores["store_key"] = np.arange(1, len(items) + 1), np.arange(1, len(stores) + 1)
        con.executemany("INSERT INTO dim_item VALUES (?,?,?,?)", items[["item_key", "item_id", "dept_id", "cat_id"]].itertuples(index=False))
        con.executemany("INSERT INTO dim_store VALUES (?,?,?)", stores[["store_key", "store_id", "state_id"]].itertuples(index=False))
        w = panel.weeks
        con.executemany("INSERT INTO dim_week VALUES (?,?,?,?,?,?,?,?,?)", [
            (int(r.week_idx), int(r.wm_yr_wk), r.week_start.strftime("%Y-%m-%d"), int(r.month), int(r.year),
             int(r.snap_days_CA), int(r.snap_days_TX), int(r.snap_days_WI), int(r.event_days)) for r in w.itertuples()])
        dd = dim_date[["date", "wm_yr_wk", "week_idx", "weekday", "wday", "month", "year", "event_name_1", "event_type_1",
                       "event_name_2", "event_type_2", "snap_CA", "snap_TX", "snap_WI"]].astype(object).where(lambda x: x.notna(), None)
        con.executemany("INSERT INTO dim_date VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", dd.itertuples(index=False))

        # ---- weekly fact: only on-sale series-weeks, inserted in primary-key order (fast)
        ikey = items.set_index("item_id")["item_key"].reindex(s["item_id"]).to_numpy()
        skey = stores.set_index("store_id")["store_key"].reindex(s["store_id"]).to_numpy()
        si, wi = np.nonzero(panel.onsale)
        order = np.lexsort((wi, skey[si], ikey[si]))
        si, wi = si[order], wi[order]
        units = panel.units[si, wi]
        price = np.round(panel.price[si, wi].astype(np.float64), 2)
        revenue = np.round(units * price, 2)
        for a in range(0, len(si), CHUNK):
            b = a + CHUNK
            con.executemany("INSERT INTO fact_weekly_sales VALUES (?,?,?,?,?,?)",
                            zip(ikey[si[a:b]].tolist(), skey[si[a:b]].tolist(), wi[a:b].tolist(), units[a:b].tolist(),
                                price[a:b].tolist(), revenue[a:b].tolist()))

        # ---- daily fact
        sk = stores.set_index("store_id")["store_key"]
        d = daily.copy()
        d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
        d["store_key"] = d["store_id"].map(sk)
        con.executemany("INSERT INTO fact_daily_sales VALUES (?,?,?,?,?)",
                        d[["date", "store_key", "dept_id", "units", "revenue"]].itertuples(index=False))
        con.commit()
    finally:
        con.close()
    return db_path


def parse_named_queries(sql_text):
    """Split a .sql file into {query_name: sql} using the '-- name: xxx' markers."""
    parts = re.split(r"^--\s*name:\s*(\w+)\s*$", sql_text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def run_query(sql, db_path=None):
    con = sqlite3.connect(db_path or cfg.DB_PATH)
    try:
        return pd.read_sql_query(sql, con)
    finally:
        con.close()


def run_all_sql_files(db_path=None, out_dir=None):
    """Run every query in sql/01..06 and save results as CSV. Returns {file__query: DataFrame}."""
    out_dir = out_dir or cfg.SQL_RESULTS
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for f in sorted(cfg.SQL_DIR.glob("0[1-9]_*.sql")):
        for name, sql in parse_named_queries(f.read_text(encoding="utf-8")).items():
            df = run_query(sql, db_path)
            key = f"{f.stem}__{name}"
            df.to_csv(out_dir / f"{key}.csv", index=False)
            results[key] = df
    return results
