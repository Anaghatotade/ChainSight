# ChainSight — Architecture

## System overview

```mermaid
graph TB
    subgraph Client["Browser"]
        UI[Next.js 14 + TypeScript<br/>Recharts, Tailwind CSS]
    end

    subgraph Backend["FastAPI Backend"]
        API[REST API Layer<br/>JWT Auth, Pydantic Validation]
        SVC[Services Layer<br/>Supplier Scoring, Inventory Analysis,<br/>What-If Simulator, Recommendations]
        ML[ML Layer<br/>RandomForest Forecasting<br/>IsolationForest Anomalies<br/>RandomForest Risk Classifier]
        ETL[ETL Layer<br/>Synthetic Data Simulation<br/>Discrete-Event Generator]
    end

    subgraph Data["PostgreSQL"]
        CORE[(Core Tables<br/>suppliers, products,<br/>warehouses)]
        FACT[(Fact Tables<br/>inventory_snapshots,<br/>demand_history, purchase_orders)]
        MLOUT[(ML Output Tables<br/>demand_forecasts, anomalies,<br/>stockout_risk_scores, recommendations)]
    end

    UI -->|HTTPS / JWT Bearer Token| API
    API --> SVC
    API --> MLOUT
    SVC --> FACT
    SVC --> CORE
    ML -->|writes predictions| MLOUT
    ML -->|reads training data| FACT
    ETL -->|seeds| CORE
    ETL -->|seeds| FACT

    style UI fill:#2456f5,color:#fff
    style API fill:#1a3fd1,color:#fff
    style SVC fill:#1a3fd1,color:#fff
    style ML fill:#7c3aed,color:#fff
    style ETL fill:#7c3aed,color:#fff
    style CORE fill:#0f766e,color:#fff
    style FACT fill:#0f766e,color:#fff
    style MLOUT fill:#0f766e,color:#fff
```

Three containers, orchestrated by Docker Compose: a Next.js frontend, a
FastAPI backend (which also owns the ETL simulation and ML pipeline as
Python modules invoked at startup / on demand), and PostgreSQL.

## Database schema (entity-relationship diagram)

```mermaid
erDiagram
    SUPPLIERS ||--o{ PRODUCTS : supplies
    SUPPLIERS ||--o{ PURCHASE_ORDERS : receives
    SUPPLIERS ||--o{ QUALITY_RECORDS : "inspected for"
    WAREHOUSES ||--o{ INVENTORY_SNAPSHOTS : stores
    WAREHOUSES ||--o{ DEMAND_HISTORY : fulfills
    WAREHOUSES ||--o{ PURCHASE_ORDERS : "delivered to"
    PRODUCTS ||--o{ INVENTORY_SNAPSHOTS : tracked_in
    PRODUCTS ||--o{ DEMAND_HISTORY : demanded_as
    PRODUCTS ||--o{ PURCHASE_ORDER_ITEMS : ordered_as
    PRODUCTS ||--o{ CUSTOMER_ORDERS : sold_as
    PRODUCTS ||--o{ STOCKOUT_RISK_SCORES : scored_as
    PRODUCTS ||--o{ DEMAND_FORECASTS : forecast_for
    PURCHASE_ORDERS ||--o{ PURCHASE_ORDER_ITEMS : contains
    PURCHASE_ORDERS ||--o{ SHIPMENTS : ships_via

    SUPPLIERS {
        int id PK
        string supplier_code
        string name
        string region
        string risk_tier
        numeric on_time_rate
        numeric cost_index
    }
    PRODUCTS {
        int id PK
        string sku
        string name
        int primary_supplier_id FK
        string abc_class
        int safety_stock_units
        int reorder_point_units
    }
    WAREHOUSES {
        int id PK
        string warehouse_code
        string region
        int capacity_units
    }
    INVENTORY_SNAPSHOTS {
        int id PK
        int product_id FK
        int warehouse_id FK
        date snapshot_date
        int on_hand_units
        boolean stockout_flag
    }
    DEMAND_HISTORY {
        int id PK
        int product_id FK
        int warehouse_id FK
        date demand_date
        int units_demanded
        int units_fulfilled
    }
    PURCHASE_ORDERS {
        int id PK
        string po_number
        int supplier_id FK
        int warehouse_id FK
        date promised_date
        date actual_delivery_date
        string status
    }
    PURCHASE_ORDER_ITEMS {
        int id PK
        int purchase_order_id FK
        int product_id FK
        int quantity
        numeric unit_cost
    }
    SHIPMENTS {
        int id PK
        int purchase_order_id FK
        string carrier
        string status
        int delay_days
    }
    QUALITY_RECORDS {
        int id PK
        int supplier_id FK
        int product_id FK
        numeric defect_rate
    }
    CUSTOMER_ORDERS {
        int id PK
        int product_id FK
        int warehouse_id FK
        boolean on_time
        boolean in_full
    }
    STOCKOUT_RISK_SCORES {
        int id PK
        int product_id FK
        numeric risk_probability
        string risk_level
        json explanation_json
    }
    DEMAND_FORECASTS {
        int id PK
        int product_id FK
        date forecast_date
        numeric forecast_units
    }
```

Full DDL with indexes and views: [`db/init.sql`](../db/init.sql).

## Data flow: from raw simulation to a dashboard number

```mermaid
sequenceDiagram
    participant ETL as ETL Generator
    participant DB as PostgreSQL
    participant Pipeline as ML Pipeline
    participant API as FastAPI
    participant UI as Next.js Frontend

    ETL->>DB: Simulate 365 days (demand, inventory, POs, shipments, quality)
    Note over ETL,DB: Discrete-event simulation:<br/>demand depletes inventory -> triggers reorder<br/>-> supplier reliability determines delay/defects

    Pipeline->>DB: Read historical demand + inventory + supplier data
    Pipeline->>Pipeline: Train RandomForest (demand forecast)
    Pipeline->>Pipeline: Run IsolationForest (anomaly detection)
    Pipeline->>Pipeline: Train RandomForest Classifier (stockout risk)
    Pipeline->>Pipeline: Generate rule-based recommendations
    Pipeline->>DB: Persist forecasts, anomalies, risk scores, recommendations

    UI->>API: GET /api/v1/kpis/summary (JWT authenticated)
    API->>DB: Aggregate SQL query
    DB-->>API: KPI results
    API-->>UI: JSON response

    UI->>API: POST /api/v1/simulator/run (what-if scenario)
    API->>API: Run baseline vs scenario simulation (same seed)
    API-->>UI: Projected inventory, service level, cost delta
```

The key design point: the ETL step is a genuine day-by-day simulation, not
independently randomized columns. Demand depletes real inventory; crossing
a reorder point triggers a real purchase order; a supplier's latent
reliability parameter determines whether that order arrives late or fails
inspection. That causal structure is what makes the downstream ML meaningful
— the models are learning real (simulated) patterns, not noise.
