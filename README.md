# ChainSight — Supply Chain Intelligence & Decision Support Platform

![CI](https://github.com/Anaghatotade/ChainSight/actions/workflows/ci.yml/badge.svg)

A full-stack, production-style **Supply Chain Analytics + ML Decision Support** platform.
Built to demonstrate end-to-end system design across frontend engineering, backend/API
design, relational database engineering, ETL, statistics, machine learning, and BI —
suitable for both SDE and Data/Business Analyst portfolios.

> **Tech stack:** Next.js 14 (TypeScript) · FastAPI (Python) · PostgreSQL · Pandas ·
> Scikit-learn · Docker / Docker Compose

---

## Screenshots

<!--
  Add your own captures to docs/screenshots/ using the exact filenames below —
  see docs/screenshots/README.md for a step-by-step guide. Until then, these
  will show as broken image links, which is expected.
-->

| | |
|---|---|
| **Dashboard** ![Dashboard](docs/screenshots/dashboard.png) | **Supplier Scoring** ![Suppliers](docs/screenshots/suppliers.png) |
| **Inventory Health** ![Inventory](docs/screenshots/inventory.png) | **Demand Forecasting** ![Forecasting](docs/screenshots/forecasting.png) |
| **Stockout Risk (with explanations)** ![Risk](docs/screenshots/risk.png) | **What-If Simulator** ![Simulator](docs/screenshots/simulator.png) |

---


## 1. What this platform does

| Capability | Description |
|---|---|
| **Executive KPI Dashboard** | Fill rate, OTIF, inventory turnover, inventory value, lead time, at-risk SKU count — all computed live via SQL, not hardcoded |
| **Supplier Performance Scoring** | Weighted composite scorecard (on-time delivery, quality, cost, lead-time consistency) with per-supplier radar breakdown |
| **Inventory Analysis** | Days-of-supply, ABC classification (Pareto revenue analysis), health status (critical/low/healthy/overstock) |
| **Demand Forecasting** | RandomForest regression over lag + calendar features, 30-day horizon, confidence bands, backtested MAE/MAPE |
| **Anomaly Detection** | IsolationForest + rolling statistical bounds across demand spikes/drops, supplier delivery delays, and quality defect rates |
| **Stockout Risk Prediction** | RandomForest classifier estimating P(stockout within 14 days) **with explainability** — a ranked, human-readable breakdown of *why* each SKU is at risk |
| **What-If Simulator** | Interactive scenario engine: adjust demand, lead time, supplier capacity, safety stock, and cost, then compare projected inventory, service level, stockout days, and procurement cost vs. baseline |
| **Recommendation Engine** | Rule-based synthesis of actionable insights from all of the above, with priority and estimated impact |
| **Auth & RBAC** | JWT-based auth with admin / analyst / viewer roles |

Every number on every page is computed from the underlying PostgreSQL data at request
time (or from a persisted ML pipeline run) — there are no hardcoded metrics or decorative
buttons.

---

## 2. Architecture

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

Full architecture docs, including the database ER diagram and an end-to-end
data-flow sequence diagram, live in [`docs/architecture.md`](docs/architecture.md).

**Data flow:**
1. `app/etl/generate_synthetic_data.py` runs a day-by-day discrete-event simulation
   (365 days) that generates suppliers → products → demand → inventory positions →
   purchase orders → shipments → quality inspections, all **causally consistent**
   (e.g., a stockout only occurs when simulated demand actually exceeds simulated
   on-hand inventory, driven by each supplier's latent reliability/lead-time
   parameters) rather than independently randomized columns.
2. `app/ml/pipeline.py` then trains/runs the forecasting, anomaly detection, and
   stockout-risk models against that data and persists results to dedicated tables
   (`demand_forecasts`, `anomalies`, `stockout_risk_scores`, `recommendations`) so
   dashboard reads are fast.
3. The FastAPI layer exposes this via versioned REST endpoints (`/api/v1/...`),
   protected by JWT auth.
4. The Next.js frontend consumes the API and renders interactive, filterable views.

---

## 3. Quick start (Docker — recommended)

```bash
git clone <this-repo> supply-chain-platform
cd supply-chain-platform
cp .env.example .env        # adjust SECRET_KEY for production use
docker compose up --build
```

First boot takes **1–3 minutes** while the backend generates the synthetic dataset
(365 days × ~90 products × up to 3 warehouses) and runs the analytics pipeline. Watch
the logs:

```bash
docker compose logs -f backend
```

Once you see `Starting API server...` and `Application startup complete`, open:

- **Frontend:** http://localhost:3000
- **Backend API docs (Swagger):** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

### Demo accounts (seeded automatically)

| Email | Password | Role |
|---|---|---|
| `admin@chainsight.io` | `Admin123!` | admin (can trigger pipeline re-runs) |
| `analyst@chainsight.io` | `Analyst123!` | analyst |
| `viewer@chainsight.io` | `Viewer123!` | viewer |

To force-regenerate the dataset on next boot: set `FORCE_RESEED=true` in `.env` and
run `docker compose up --build` again.

---

## 4. Running locally without Docker

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# point DATABASE_URL at a local Postgres instance, e.g.:
export DATABASE_URL=postgresql://chainsight_user:chainsight_pass@localhost:5432/chainsight_db

python -m app.etl.generate_synthetic_data   # seeds ~1-3 min
python -m app.etl.seed_users
python -m app.ml.pipeline                   # trains models, persists analytics

uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
export NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

### Tests
```bash
cd backend
pytest -v
```
Covers auth flows (registration/login/JWT validation) and the analytics/ML service
layer (supplier scoring, inventory classification, the What-If simulator, the
forecasting fallback + RandomForest paths, and the risk model's explainability
output) independent of the seeded database.

---

## 5. Database design

See [`db/init.sql`](./db/init.sql) for the full DDL. Highlights:

- **Normalized core entities:** `suppliers`, `products`, `warehouses`, with proper
  foreign keys and cascade rules.
- **Time-series facts:** `inventory_snapshots`, `demand_history`, indexed on
  `(product_id, snapshot_date)` / `(product_id, demand_date)` for fast trend queries.
- **Transactional history:** `purchase_orders` → `purchase_order_items`, `shipments`,
  `quality_records`, `customer_orders` — the full inbound/outbound trail used to
  compute OTIF, fill rate, and supplier scorecards.
- **ML output tables:** `demand_forecasts`, `anomalies`, `stockout_risk_scores`
  (with a `JSONB explanation_json` column for the explainability payload),
  `recommendations`, `ml_runs` (audit trail of pipeline executions).
- **Analytical views:** `vw_supplier_performance`, `vw_inventory_health` for
  ad-hoc SQL exploration.

---

## 6. Machine learning components

| Model | Algorithm | Location |
|---|---|---|
| Demand forecasting | RandomForestRegressor over lag(1,2,3,7,14,21,28) + rolling mean/std + calendar features; exponential-smoothing fallback for short series | `backend/app/ml/forecasting.py` |
| Anomaly detection | IsolationForest + rolling z-score bounds, applied separately to demand, supplier delay, and defect-rate series | `backend/app/ml/anomaly_detection.py` |
| Stockout risk | RandomForestClassifier, label = "stockout occurs within next 14 days", features = days-of-supply, demand volatility, lead time & variability, supplier on-time rate, safety-stock coverage, defect rate, demand trend | `backend/app/ml/risk_scoring.py` |
| Explainability | Per-prediction signed feature-contribution breakdown (feature importance × normalized deviation from the training population), rendered as plain-English factors in the UI | `risk_scoring.score_instance()` |
| What-If simulator | Deterministic, fixed-seed periodic-review / order-up-to inventory simulation, run twice (baseline vs. scenario) so random noise is held constant and only the changed levers explain the delta | `backend/app/services/simulator.py` |

All models are retrained from live data whenever `app/ml/pipeline.py` runs (also
triggerable by an admin user via `POST /api/v1/admin/run-pipeline`), so results
reflect the actual seeded dataset rather than being baked in.

---

## 7. API overview

Full interactive documentation at `/docs` (Swagger UI). Key endpoint groups:

```
POST   /api/v1/auth/register | /login          Auth
GET    /api/v1/auth/me

GET    /api/v1/kpis/summary                     Dashboard KPIs
GET    /api/v1/kpis/trends/*                    Time-series trends

GET    /api/v1/suppliers                        Supplier list
GET    /api/v1/suppliers/scores                 Composite scorecards
GET    /api/v1/suppliers/{id}                   Supplier detail + history

GET    /api/v1/inventory/health                 Inventory health & filters
GET    /api/v1/inventory/abc-analysis
GET    /api/v1/inventory/turnover-by-category

GET    /api/v1/forecasting/{product_id}/{warehouse_id}
GET    /api/v1/forecasting/accuracy/summary

GET    /api/v1/anomalies
GET    /api/v1/anomalies/summary

GET    /api/v1/risk/stockout                    Risk + explanations
GET    /api/v1/risk/summary

POST   /api/v1/simulator/run                    What-if scenario engine

GET    /api/v1/recommendations
PATCH  /api/v1/recommendations/{id}/resolve

GET    /api/v1/catalog/products | /warehouses | /categories | /regions

POST   /api/v1/admin/run-pipeline               (admin only) re-run ML pipeline
```

---

## 8. Project structure

```
supply-chain-platform/
├── docs/
│   ├── architecture.md            # architecture, ER, and data-flow diagrams
│   ├── diagrams/                  # editable .mmd Mermaid diagram sources
│   └── screenshots/                # UI screenshots (see screenshots/README.md)
├── db/
│   └── init.sql                  # full schema, indexes, views
├── backend/
│   ├── app/
│   │   ├── core/                 # config, db session, security/JWT
│   │   ├── models/                # SQLAlchemy ORM models
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   ├── api/                    # FastAPI routers (one per feature area)
│   │   ├── services/               # business logic: scoring, inventory, simulator, recommendations
│   │   ├── ml/                     # forecasting, anomaly detection, risk scoring, pipeline orchestration
│   │   ├── etl/                    # synthetic data generator, user seeding
│   │   ├── tests/                  # pytest suite
│   │   └── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── entrypoint.sh
├── frontend/
│   ├── app/                        # Next.js App Router pages (dashboard, suppliers, inventory, ...)
│   ├── components/                 # shared UI (AppShell, KPICard, Badge, Pagination, ...)
│   ├── contexts/AuthContext.tsx
│   ├── lib/                        # typed API client, CSV export utility
│   └── Dockerfile
├── .github/workflows/ci.yml       # CI: pytest, frontend build, Docker image builds
├── docker-compose.yml
└── .env.example
```

---

## 9. Design notes & tradeoffs

- **Synthetic data is simulation-driven, not column-randomized.** Inventory only
  depletes when demand is actually generated for that day; purchase orders only fire
  when a periodic review finds inventory position below the reorder point; a
  supplier's *latent* reliability and defect-rate parameters drive whether its
  orders arrive late or fail inspection. This is what makes the downstream ML
  meaningful — the model is learning real (simulated) causal patterns.
- **Explainability without a heavy SHAP dependency.** The risk model produces a
  signed, per-feature contribution using `feature_importances_` combined with each
  feature's z-score against the training population. This is a documented
  approximation (not exact Shapley values) chosen to keep the container lightweight
  and inference fast, while still answering "why is this SKU risky" in the UI.
- **The What-If simulator uses a fixed random seed per SKU** so baseline and
  scenario runs share the same demand realization — isolating the effect of the
  levers the user actually changed rather than random variance.
- **Persisted vs. live ML endpoints.** Risk scores, anomalies, and forecasts are
  precomputed by the pipeline for fast dashboard reads; the forecasting endpoint
  also supports `?live=true` to retrain on demand for a single SKU if you want to
  see the model run in real time.

---

## 10. License

MIT — built as a portfolio/demonstration project.

---

## 11. Changelog / recent improvements

- **CI pipeline** (`.github/workflows/ci.yml`): runs the backend pytest suite,
  a frontend production build + TypeScript typecheck, and Docker image builds
  on every push/PR.
- **Pagination**: `/anomalies`, `/risk/stockout`, `/inventory/health`, and
  `/recommendations` now return `{items, total, limit, offset}` instead of a
  flat list, with page controls in the UI, so these stay usable as the
  dataset grows well beyond the seeded demo size.
- **CSV export**: an "Export CSV" button on the suppliers, inventory,
  anomalies, risk, and recommendations pages converts the currently-loaded
  page of data to a downloadable `.csv` client-side — no backend endpoint
  needed.
- **Per-tab session isolation**: auth tokens moved from `localStorage` to
  `sessionStorage`, so different accounts can be signed in simultaneously in
  different browser tabs (useful for comparing admin/analyst/viewer views
  side by side) instead of one shared session across the whole browser.
- **Registration reliability fix**: `EmailStr` validation previously
  performed a live DNS/MX-record lookup on every registration by default,
  making account creation depend on the container's outbound DNS working —
  a common source of flakiness on Docker Desktop/WSL2. Deliverability
  checking is now disabled; format validation still applies.
- **Dependency security patches**: bumped `next` (14.2.5 → 14.2.35) and
  `axios` (1.7.4 → 1.20.0) to their latest patched releases within the same
  major version, and forced Next.js's internally-bundled vulnerable `postcss`
  copy to a safe version via an `overrides` entry in `package.json`. The
  handful of `next` advisories that remain per `npm audit` are scoped to
  Server Actions, Middleware, and the Image Optimization API — subsystems
  this app doesn't use (every page is a client component; no `middleware.ts`,
  no `next/image`, no Server Actions). Fully clearing those would require a
  Next.js 15+ major-version migration, tracked as a follow-up rather than
  bundled into this patch set.

