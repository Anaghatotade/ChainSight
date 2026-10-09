-- =====================================================================
-- ChainSight (SQLite) - schema for the CLEANED data
-- Ported from the original PostgreSQL db/init.sql, simplified to the 7 tables
-- this analysis needs (users, ml_runs, anomalies, risk tables, quality, customer_orders removed).
-- Dates are stored as ISO text 'YYYY-MM-DD' (SQLite has no DATE type; ISO text sorts correctly).
-- =====================================================================
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS purchase_orders;
DROP TABLE IF EXISTS inventory_policy;
DROP TABLE IF EXISTS inventory_daily;
DROP TABLE IF EXISTS demand_daily;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS warehouses;

CREATE TABLE warehouses (
    warehouse_code  TEXT PRIMARY KEY,
    warehouse_name  TEXT NOT NULL,
    region          TEXT NOT NULL,
    capacity_units  INTEGER NOT NULL
);

CREATE TABLE suppliers (
    supplier_code          TEXT PRIMARY KEY,
    supplier_name          TEXT NOT NULL,
    country                TEXT NOT NULL,
    region                 TEXT NOT NULL,
    category               TEXT NOT NULL,
    quoted_lead_time_days  INTEGER NOT NULL
);

CREATE TABLE products (
    sku            TEXT PRIMARY KEY,
    product_name   TEXT NOT NULL,
    category       TEXT NOT NULL,
    sub_category   TEXT NOT NULL,
    unit_cost      REAL NOT NULL,
    unit_price     REAL NOT NULL,
    supplier_code  TEXT NOT NULL REFERENCES suppliers(supplier_code)
);

-- one row per SKU x warehouse x day (sales / demand)
CREATE TABLE demand_daily (
    sku              TEXT NOT NULL REFERENCES products(sku),
    warehouse_code   TEXT NOT NULL REFERENCES warehouses(warehouse_code),
    date             TEXT NOT NULL,
    units_demanded   INTEGER NOT NULL CHECK (units_demanded >= 0),
    units_fulfilled  INTEGER NOT NULL CHECK (units_fulfilled >= 0 AND units_fulfilled <= units_demanded),
    promo_flag       INTEGER NOT NULL CHECK (promo_flag IN (0, 1)),
    stockout_flag    INTEGER NOT NULL CHECK (stockout_flag IN (0, 1)),
    PRIMARY KEY (sku, warehouse_code, date)
);

-- end-of-day stock level
CREATE TABLE inventory_daily (
    sku               TEXT NOT NULL REFERENCES products(sku),
    warehouse_code    TEXT NOT NULL REFERENCES warehouses(warehouse_code),
    date              TEXT NOT NULL,
    on_hand_units     INTEGER NOT NULL CHECK (on_hand_units >= 0),
    in_transit_units  INTEGER NOT NULL,
    PRIMARY KEY (sku, warehouse_code, date)
);

-- the reorder policy the company currently uses
CREATE TABLE inventory_policy (
    sku                  TEXT NOT NULL REFERENCES products(sku),
    warehouse_code       TEXT NOT NULL REFERENCES warehouses(warehouse_code),
    reorder_point_units  INTEGER NOT NULL,
    safety_stock_units   INTEGER NOT NULL,
    order_up_to_units    INTEGER NOT NULL,
    review_period_days   INTEGER NOT NULL,
    policy_set_date      TEXT NOT NULL,
    PRIMARY KEY (sku, warehouse_code)
);

-- one row per purchase order (single SKU per PO)
CREATE TABLE purchase_orders (
    po_number               TEXT PRIMARY KEY,
    supplier_code           TEXT NOT NULL REFERENCES suppliers(supplier_code),
    sku                     TEXT NOT NULL REFERENCES products(sku),
    warehouse_code          TEXT NOT NULL REFERENCES warehouses(warehouse_code),
    order_date              TEXT NOT NULL,
    promised_delivery_date  TEXT NOT NULL,
    actual_delivery_date    TEXT,                 -- NULL = not delivered yet OR invalid date (see flag)
    quantity                INTEGER NOT NULL,
    unit_cost               REAL NOT NULL,
    ship_mode               TEXT NOT NULL,
    freight_cost            REAL,
    status                  TEXT NOT NULL,
    delivery_date_invalid   INTEGER NOT NULL DEFAULT 0,
    po_value                REAL,
    promised_lead_days      INTEGER,
    actual_lead_days        INTEGER,
    delay_days              INTEGER,
    on_time_flag            REAL
);

CREATE INDEX idx_demand_date      ON demand_daily(date);
CREATE INDEX idx_demand_sku_date  ON demand_daily(sku, date);
CREATE INDEX idx_inv_date         ON inventory_daily(date);
CREATE INDEX idx_inv_sku_date     ON inventory_daily(sku, date);
CREATE INDEX idx_po_supplier      ON purchase_orders(supplier_code);
CREATE INDEX idx_po_sku           ON purchase_orders(sku);
