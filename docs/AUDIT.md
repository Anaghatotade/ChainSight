# Audit of the original ChainSight repository

Audited: the repository as cloned from `github.com/Anaghatotade/ChainSight` (last commit "Refine project description in README").
It was a full-stack web app (Next.js frontend + FastAPI backend + PostgreSQL + Docker): 89 files, about 3,000 lines of Python backend code and 29 frontend files.
**No data files were committed** - the data came from a generator script (`backend/app/etl/generate_synthetic_data.py`).

## What I found, and the decision for each part

| Area | Original content | Verdict |
|---|---|---|
| Frontend | Next.js/React app: dashboard, inventory, forecasting, risk, simulator, suppliers pages; login (JWT); CSV export | **Removed** - a web UI is not a data-analyst deliverable; charts + Excel/CSV for Power BI replace it |
| Backend API | FastAPI routers (kpis, inventory, forecasting, risk, anomalies, simulator, suppliers, auth, admin), SQLAlchemy models, Pydantic schemas, JWT/bcrypt security | **Removed** - REST + auth + ORM add nothing to the analysis story |
| Infra | `docker-compose.yml`, two Dockerfiles, `entrypoint.sh`, `add_docs.sh` (33 KB of shell that writes docs), `.env.example`, GitHub Actions CI (Postgres service) | **Removed** (no `.sh` files, no Docker, no deployment config) |
| Database | PostgreSQL `db/init.sql`, 17-table schema incl. users, ml_runs, anomalies, risk scores | **Ported to SQLite** - the 7 tables the analysis needs (`sql/00_schema.sql`); Postgres-only syntax rewritten |
| Data generator | Day-by-day simulation of demand, inventory, reorder policy, purchase orders, supplier reliability | **Reused and fixed** (`src/datagen.py`) |
| KPI logic | `api/kpis.py` SQL + `services/inventory_analysis.py` (days of supply, status) | **Reused as definitions**, re-implemented in pandas + SQLite and corrected (see bugs) |
| Reorder / safety stock | `z x sigma x sqrt(LT)` inside the generator and simulator | **Reused**, extended with review period and lead-time variability (`kpis.safety_stock`) |
| Supplier scoring | Weighted composite score (on-time, quality, cost, consistency) | **Simplified** to lead-time statistics (on-time %, delay, CV); the weights were arbitrary and quality data is outside the KPI scope |
| Forecasting | `ml/forecasting.py` - RandomForestRegressor with lag features | **Replaced** by interpretable baselines + linear regression + a NumPy MLP with proper time-based evaluation |
| Risk scoring | `ml/risk_scoring.py` - RandomForestClassifier | **Removed** (advanced ML, not needed for the story) |
| Anomaly detection | `ml/anomaly_detection.py` - IsolationForest | **Removed**; replaced by a simple, explainable typo rule in cleaning and an outlier tag in error analysis |
| Pipeline | `ml/pipeline.py` - writes forecasts/risk/anomalies back to Postgres | **Removed** (MLOps-style orchestration) |
| Simulator | `services/simulator.py` what-if scenarios | **Removed** (a web feature); `kpis.build_policy_check` answers the same "what policy do we need" question |
| Recommendations | Rule-based text engine in `services/recommendations.py` | **Idea kept**: `src/08_recommendations.py` builds recommendations from real numbers, with a value at stake each |
| Tests | Auth and service tests needing the web stack | **Replaced** by a pure-Python pytest suite (cleaning, KPI formulas, SQL vs pandas, split logic, metrics, baselines, gradient check) |
| Docs | Architecture/ER/data-flow diagrams, README with screenshots | **Replaced** by README (findings), README_SETUP, INTERVIEW_NOTES, data dictionary |

## Bugs / weaknesses found in the original (by reading the code)

1. **Only partly reproducible:** `random` and `numpy` were seeded (42), but the history was anchored to `date.today()` (so dates shifted every day) and `Faker` was not seeded (different names each run).
2. **Inventory turnover was inflated:** `api/kpis.py` divided the *sum* of COGS over the whole history by `AVG(on_hand_units * unit_cost)` over snapshot rows, i.e. by the value of one average SKU-warehouse-day instead of the total inventory (and the COGS was not annualised although the comment said so). That overstates turnover by roughly the number of SKU-warehouse pairs. Fixed: average of the *daily total* inventory value, annualised.
3. **ABC window frame:** the cumulative revenue used `SUM(...) OVER (ORDER BY revenue DESC)` - the default `RANGE` frame with no tie-break (tied SKUs get the same cumulative value) - and the class was assigned on cumulative share *including* the item, so a single dominant item could be demoted to B. Fixed with a `ROWS` frame, a tie-break and share-before-item (tests in `tests/test_kpis.py`).
4. **Lost purchase-order arrivals:** pending arrivals were stored in a dict keyed by arrival day and overwritten when two orders landed on the same day, silently losing the earlier order's inventory. Fixed: quantities accumulate.
5. **Recommendation text bug:** one recommendation multiplied inventory by zero, so it printed "~$0 in other priorities".
6. **Safety stock too simple:** ignored the review period and lead-time variability. The generator's policy deliberately keeps this simplification so the analysis can show its consequence.
7. **No promo flag recorded:** promotions affected demand but were not stored, so they could not be used as a forecast feature. Now recorded.
8. **No time-based evaluation:** the RandomForest forecast had no train/dev/test discipline and no baseline comparison, so "good" was undefined.

## What was reused (in spirit and logic)

Simulation structure (demand -> inventory -> weekly review -> purchase order -> supplier lead time/reliability), KPI definitions, the ABC idea, the reorder-point / safety-stock formula, the master-data shape (90 SKUs x 24 suppliers x 5 warehouses), category list and supplier regions.

## Result

Everything non-analytical is gone. The remaining project is Python + pandas + NumPy + SQLite + matplotlib/seaborn: 10 numbered scripts, 5 notebooks, 7 SQL files and a pytest suite. The original code remains available in the git history (`git log`, `git show HEAD:backend/app/...`).
