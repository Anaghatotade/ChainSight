-- =====================================================================
-- ChainSight — Supply Chain Intelligence & Decision Support Platform
-- Database Schema (PostgreSQL)
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------
-- Users / Auth
-- ---------------------------------------------------------------------
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(50) NOT NULL DEFAULT 'analyst',  -- admin, analyst, viewer
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------
-- Suppliers
-- ---------------------------------------------------------------------
CREATE TABLE suppliers (
    id                  SERIAL PRIMARY KEY,
    supplier_code       VARCHAR(20) UNIQUE NOT NULL,
    name                VARCHAR(255) NOT NULL,
    country             VARCHAR(100) NOT NULL,
    region              VARCHAR(100) NOT NULL,
    category            VARCHAR(100) NOT NULL,       -- e.g. Electronics, Raw Material
    risk_tier           VARCHAR(20) NOT NULL DEFAULT 'medium', -- low, medium, high
    on_time_rate        NUMERIC(5,4),                -- computed/rollup, %
    quality_score       NUMERIC(5,2),                -- 0-100 rollup
    avg_lead_time_days  NUMERIC(6,2),
    lead_time_std_days  NUMERIC(6,2),
    cost_index          NUMERIC(6,3) DEFAULT 1.0,     -- relative cost competitiveness
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_suppliers_region ON suppliers(region);
CREATE INDEX idx_suppliers_risk_tier ON suppliers(risk_tier);

-- ---------------------------------------------------------------------
-- Warehouses
-- ---------------------------------------------------------------------
CREATE TABLE warehouses (
    id            SERIAL PRIMARY KEY,
    warehouse_code VARCHAR(20) UNIQUE NOT NULL,
    name          VARCHAR(255) NOT NULL,
    region        VARCHAR(100) NOT NULL,
    capacity_units INTEGER NOT NULL
);

-- ---------------------------------------------------------------------
-- Products
-- ---------------------------------------------------------------------
CREATE TABLE products (
    id                  SERIAL PRIMARY KEY,
    sku                 VARCHAR(30) UNIQUE NOT NULL,
    name                VARCHAR(255) NOT NULL,
    category            VARCHAR(100) NOT NULL,
    unit_cost           NUMERIC(10,2) NOT NULL,
    unit_price          NUMERIC(10,2) NOT NULL,
    primary_supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    abc_class           CHAR(1),                 -- A, B, C (computed)
    safety_stock_units  INTEGER NOT NULL DEFAULT 0,
    reorder_point_units INTEGER NOT NULL DEFAULT 0,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_supplier ON products(primary_supplier_id);

-- ---------------------------------------------------------------------
-- Inventory snapshots (daily)
-- ---------------------------------------------------------------------
CREATE TABLE inventory_snapshots (
    id                SERIAL PRIMARY KEY,
    product_id        INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    warehouse_id      INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    snapshot_date     DATE NOT NULL,
    on_hand_units     INTEGER NOT NULL,
    in_transit_units  INTEGER NOT NULL DEFAULT 0,
    allocated_units   INTEGER NOT NULL DEFAULT 0,
    stockout_flag     BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(product_id, warehouse_id, snapshot_date)
);
CREATE INDEX idx_inv_snap_date ON inventory_snapshots(snapshot_date);
CREATE INDEX idx_inv_snap_product ON inventory_snapshots(product_id);
CREATE INDEX idx_inv_snap_product_date ON inventory_snapshots(product_id, snapshot_date);

-- ---------------------------------------------------------------------
-- Demand history (actual daily demand / sales per product)
-- ---------------------------------------------------------------------
CREATE TABLE demand_history (
    id             SERIAL PRIMARY KEY,
    product_id     INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    warehouse_id   INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    demand_date    DATE NOT NULL,
    units_demanded INTEGER NOT NULL,
    units_fulfilled INTEGER NOT NULL,
    UNIQUE(product_id, warehouse_id, demand_date)
);
CREATE INDEX idx_demand_date ON demand_history(demand_date);
CREATE INDEX idx_demand_product_date ON demand_history(product_id, demand_date);

-- ---------------------------------------------------------------------
-- Purchase Orders + line items
-- ---------------------------------------------------------------------
CREATE TABLE purchase_orders (
    id              SERIAL PRIMARY KEY,
    po_number       VARCHAR(30) UNIQUE NOT NULL,
    supplier_id     INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    warehouse_id    INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    order_date      DATE NOT NULL,
    promised_date   DATE NOT NULL,
    actual_delivery_date DATE,
    status          VARCHAR(20) NOT NULL DEFAULT 'open', -- open, in_transit, delivered, cancelled, delayed
    total_cost      NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_po_supplier ON purchase_orders(supplier_id);
CREATE INDEX idx_po_status ON purchase_orders(status);
CREATE INDEX idx_po_order_date ON purchase_orders(order_date);

CREATE TABLE purchase_order_items (
    id              SERIAL PRIMARY KEY,
    purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    quantity        INTEGER NOT NULL,
    unit_cost       NUMERIC(10,2) NOT NULL,
    quantity_received INTEGER NOT NULL DEFAULT 0,
    defect_units    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_poi_po ON purchase_order_items(purchase_order_id);
CREATE INDEX idx_poi_product ON purchase_order_items(product_id);

-- ---------------------------------------------------------------------
-- Shipments (inbound from supplier -> warehouse)
-- ---------------------------------------------------------------------
CREATE TABLE shipments (
    id                  SERIAL PRIMARY KEY,
    purchase_order_id   INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    carrier             VARCHAR(100) NOT NULL,
    ship_date           DATE NOT NULL,
    expected_arrival    DATE NOT NULL,
    actual_arrival      DATE,
    mode                VARCHAR(20) NOT NULL DEFAULT 'ocean', -- ocean, air, road, rail
    status              VARCHAR(20) NOT NULL DEFAULT 'in_transit', -- in_transit, delivered, delayed, lost
    delay_days          INTEGER NOT NULL DEFAULT 0,
    freight_cost        NUMERIC(10,2) NOT NULL DEFAULT 0
);
CREATE INDEX idx_shipments_po ON shipments(purchase_order_id);
CREATE INDEX idx_shipments_status ON shipments(status);

-- ---------------------------------------------------------------------
-- Quality inspection records
-- ---------------------------------------------------------------------
CREATE TABLE quality_records (
    id              SERIAL PRIMARY KEY,
    supplier_id     INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    inspection_date DATE NOT NULL,
    units_inspected INTEGER NOT NULL,
    units_defective INTEGER NOT NULL,
    defect_rate     NUMERIC(6,4) NOT NULL,
    root_cause      VARCHAR(255)
);
CREATE INDEX idx_quality_supplier ON quality_records(supplier_id);
CREATE INDEX idx_quality_date ON quality_records(inspection_date);

-- ---------------------------------------------------------------------
-- Customer orders (outbound demand fulfillment) - used for OTIF, fill-rate
-- ---------------------------------------------------------------------
CREATE TABLE customer_orders (
    id              SERIAL PRIMARY KEY,
    order_number    VARCHAR(30) UNIQUE NOT NULL,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    warehouse_id    INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    order_date      DATE NOT NULL,
    requested_qty   INTEGER NOT NULL,
    shipped_qty     INTEGER NOT NULL DEFAULT 0,
    promised_date   DATE NOT NULL,
    shipped_date    DATE,
    on_time         BOOLEAN,
    in_full         BOOLEAN
);
CREATE INDEX idx_corders_date ON customer_orders(order_date);
CREATE INDEX idx_corders_product ON customer_orders(product_id);

-- ---------------------------------------------------------------------
-- Model registry / ML run metadata (for traceability of ML outputs)
-- ---------------------------------------------------------------------
CREATE TABLE ml_runs (
    id            SERIAL PRIMARY KEY,
    model_name    VARCHAR(100) NOT NULL,   -- forecast, anomaly, stockout_risk
    run_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    metrics_json  JSONB,
    notes         TEXT
);

-- ---------------------------------------------------------------------
-- Precomputed stockout risk (persisted so API reads are fast & explainable)
-- ---------------------------------------------------------------------
CREATE TABLE stockout_risk_scores (
    id                SERIAL PRIMARY KEY,
    product_id        INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    warehouse_id      INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    as_of_date        DATE NOT NULL,
    risk_probability  NUMERIC(6,4) NOT NULL,
    risk_level        VARCHAR(20) NOT NULL,   -- low, medium, high, critical
    days_of_supply    NUMERIC(8,2),
    explanation_json  JSONB,                  -- feature contributions for explainability
    UNIQUE(product_id, warehouse_id, as_of_date)
);
CREATE INDEX idx_risk_asof ON stockout_risk_scores(as_of_date);
CREATE INDEX idx_risk_level ON stockout_risk_scores(risk_level);

-- ---------------------------------------------------------------------
-- Anomalies detected in operational metrics
-- ---------------------------------------------------------------------
CREATE TABLE anomalies (
    id              SERIAL PRIMARY KEY,
    entity_type     VARCHAR(30) NOT NULL,   -- supplier, product, shipment
    entity_id       INTEGER NOT NULL,
    metric_name     VARCHAR(100) NOT NULL,
    detected_date   DATE NOT NULL,
    metric_value    NUMERIC(12,4),
    expected_range_low NUMERIC(12,4),
    expected_range_high NUMERIC(12,4),
    anomaly_score   NUMERIC(8,4),
    severity        VARCHAR(20) NOT NULL,  -- low, medium, high
    description     TEXT
);
CREATE INDEX idx_anomalies_date ON anomalies(detected_date);
CREATE INDEX idx_anomalies_entity ON anomalies(entity_type, entity_id);

-- ---------------------------------------------------------------------
-- Demand forecasts (persisted output of ML forecasting model)
-- ---------------------------------------------------------------------
CREATE TABLE demand_forecasts (
    id              SERIAL PRIMARY KEY,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    warehouse_id    INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    forecast_date   DATE NOT NULL,
    forecast_units  NUMERIC(10,2) NOT NULL,
    lower_bound     NUMERIC(10,2) NOT NULL,
    upper_bound     NUMERIC(10,2) NOT NULL,
    model_name      VARCHAR(50) NOT NULL DEFAULT 'random_forest',
    generated_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(product_id, warehouse_id, forecast_date, model_name)
);
CREATE INDEX idx_forecast_date ON demand_forecasts(forecast_date);
CREATE INDEX idx_forecast_product ON demand_forecasts(product_id);

-- ---------------------------------------------------------------------
-- Recommendations (actionable insights engine output)
-- ---------------------------------------------------------------------
CREATE TABLE recommendations (
    id              SERIAL PRIMARY KEY,
    category        VARCHAR(50) NOT NULL,  -- inventory, supplier, procurement, quality
    entity_type     VARCHAR(30),
    entity_id       INTEGER,
    priority        VARCHAR(20) NOT NULL,  -- low, medium, high, critical
    title           VARCHAR(255) NOT NULL,
    description     TEXT NOT NULL,
    estimated_impact TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved        BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_reco_priority ON recommendations(priority);
CREATE INDEX idx_reco_category ON recommendations(category);

-- ---------------------------------------------------------------------
-- Useful analytical views
-- ---------------------------------------------------------------------

-- Supplier on-time & quality rollup view
CREATE OR REPLACE VIEW vw_supplier_performance AS
SELECT
    s.id AS supplier_id,
    s.name,
    s.region,
    s.category,
    COUNT(DISTINCT po.id) AS total_orders,
    ROUND(AVG(CASE WHEN po.actual_delivery_date IS NOT NULL AND po.actual_delivery_date <= po.promised_date THEN 1.0 ELSE 0.0 END)::numeric, 4) AS on_time_rate,
    ROUND(AVG(GREATEST(po.actual_delivery_date - po.promised_date, 0))::numeric, 2) AS avg_delay_days,
    ROUND(AVG(qr.defect_rate)::numeric, 4) AS avg_defect_rate,
    ROUND(AVG(s.cost_index)::numeric, 3) AS cost_index
FROM suppliers s
LEFT JOIN purchase_orders po ON po.supplier_id = s.id AND po.actual_delivery_date IS NOT NULL
LEFT JOIN quality_records qr ON qr.supplier_id = s.id
GROUP BY s.id, s.name, s.region, s.category;

-- Product inventory health view
CREATE OR REPLACE VIEW vw_inventory_health AS
SELECT
    p.id AS product_id,
    p.sku,
    p.name,
    p.abc_class,
    p.safety_stock_units,
    p.reorder_point_units,
    inv.warehouse_id,
    inv.on_hand_units,
    inv.in_transit_units,
    inv.snapshot_date
FROM products p
JOIN inventory_snapshots inv ON inv.product_id = p.id;
