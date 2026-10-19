-- =====================================================================
-- M5 retail analytics (SQLite) - star schema for the CLEANED real data
--   dim_item, dim_store, dim_week, dim_date        (descriptions)
--   fact_weekly_sales   grain: item x store x week (ONLY weeks the item was on sale, i.e. with a price)
--   fact_daily_sales    grain: date x store x department (small daily aggregate)
-- Dates are stored as ISO text 'YYYY-MM-DD' (SQLite has no DATE type; ISO text sorts correctly).
-- =====================================================================
PRAGMA foreign_keys = OFF;   -- switched off while bulk loading; 06_data_quality_checks.sql re-checks every key

DROP TABLE IF EXISTS fact_daily_sales;
DROP TABLE IF EXISTS fact_weekly_sales;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_week;
DROP TABLE IF EXISTS dim_store;
DROP TABLE IF EXISTS dim_item;

CREATE TABLE dim_item (
    item_key  INTEGER PRIMARY KEY,
    item_id   TEXT NOT NULL UNIQUE,      -- e.g. FOODS_3_090
    dept_id   TEXT NOT NULL,             -- e.g. FOODS_3
    cat_id    TEXT NOT NULL              -- FOODS / HOUSEHOLD / HOBBIES
);

CREATE TABLE dim_store (
    store_key INTEGER PRIMARY KEY,
    store_id  TEXT NOT NULL UNIQUE,      -- e.g. CA_1
    state_id  TEXT NOT NULL              -- CA / TX / WI
);

CREATE TABLE dim_week (
    week_idx     INTEGER PRIMARY KEY,    -- 0 = first full week (Saturday 2011-01-29)
    wm_yr_wk     INTEGER NOT NULL UNIQUE,
    week_start   TEXT NOT NULL,
    month        INTEGER NOT NULL,       -- month of the middle of the week
    year         INTEGER NOT NULL,
    snap_days_ca INTEGER NOT NULL,
    snap_days_tx INTEGER NOT NULL,
    snap_days_wi INTEGER NOT NULL,
    event_days   INTEGER NOT NULL
);

CREATE TABLE dim_date (
    date         TEXT PRIMARY KEY,
    wm_yr_wk     INTEGER NOT NULL,
    week_idx     INTEGER NOT NULL,
    weekday      TEXT NOT NULL,
    wday         INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    year         INTEGER NOT NULL,
    event_name_1 TEXT, event_type_1 TEXT, event_name_2 TEXT, event_type_2 TEXT,
    snap_CA      INTEGER NOT NULL, snap_TX INTEGER NOT NULL, snap_WI INTEGER NOT NULL
);

CREATE TABLE fact_weekly_sales (
    item_key   INTEGER NOT NULL REFERENCES dim_item(item_key),
    store_key  INTEGER NOT NULL REFERENCES dim_store(store_key),
    week_idx   INTEGER NOT NULL REFERENCES dim_week(week_idx),
    units      INTEGER NOT NULL CHECK (units >= 0),
    sell_price REAL    NOT NULL CHECK (sell_price > 0),
    revenue    REAL    NOT NULL,         -- units x sell_price
    PRIMARY KEY (item_key, store_key, week_idx)
) WITHOUT ROWID;
CREATE INDEX ix_fws_store_week ON fact_weekly_sales (store_key, week_idx);

CREATE TABLE fact_daily_sales (
    date      TEXT    NOT NULL REFERENCES dim_date(date),
    store_key INTEGER NOT NULL REFERENCES dim_store(store_key),
    dept_id   TEXT    NOT NULL,
    units     INTEGER NOT NULL CHECK (units >= 0),
    revenue   REAL    NOT NULL,
    PRIMARY KEY (date, store_key, dept_id)
) WITHOUT ROWID;
