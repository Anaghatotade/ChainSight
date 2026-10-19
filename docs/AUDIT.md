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
| Database | PostgreSQL `db/init.sql`, 17-table schema incl. users, ml_runs, anomalies, risk scores | **Ported to SQLite** - a small star schema for the analysis (`sql/00_schema.sql`, now item / store / week / date dimensions and weekly + daily facts); Postgres-only syntax rewritten |
| Data generator | Day-by-day simulation of demand, inventory, reorder policy, purchase orders, supplier reliability | **Reused first, then retired**: the project initially ran on this (fixed) simulation; it was replaced by the real Kaggle M5 data (see part 2) and `datagen.py` was deleted |
| KPI logic | `api/kpis.py` SQL + `services/inventory_analysis.py` (days of supply, status) | **Reused as definitions**, re-implemented in pandas + SQLite and corrected (see bugs). Fill rate / turnover / days of inventory need stock data, which the real M5 data lacks, so they are no longer computed |
| Reorder / safety stock | `z x sigma x sqrt(LT)` inside the generator and simulator | **Reused**, extended with review period and lead-time variability (`kpis.safety_stock`) |
| Supplier scoring | Weighted composite score (on-time, quality, cost, consistency) | **Removed** - arbitrary weights, and the real data has no suppliers |
| Forecasting | `ml/forecasting.py` - RandomForestRegressor with lag features | **Replaced** by interpretable baselines + linear regression + a NumPy MLP with proper time-based evaluation |
| Risk scoring | `ml/risk_scoring.py` - RandomForestClassifier | **Removed** (advanced ML, not needed for the story) |
| Anomaly detection | `ml/anomaly_detection.py` - IsolationForest | **Removed**; replaced by a simple, explainable typo rule in cleaning and an outlier tag in error analysis |
| Pipeline | `ml/pipeline.py` - writes forecasts/risk/anomalies back to Postgres | **Removed** (MLOps-style orchestration) |
| Simulator | `services/simulator.py` what-if scenarios | **Removed** (a web feature); `src/policy_sim.py` replays real demand through an order-up-to policy with an *assumed* lead time (clearly labelled) |
| Recommendations | Rule-based text engine in `services/recommendations.py` | **Idea kept**: `src/08_recommendations.py` builds recommendations from real numbers, with a value at stake each |
| Tests | Auth and service tests needing the web stack | **Replaced** by a pure-Python pytest suite on tiny hand-made M5-style data (cleaning rules, KPI formulas, SQL vs pandas, split logic, metrics, baselines, gradient check) |
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

KPI definitions, the ABC idea, the reorder-point / safety-stock formula (now with an explicit, assumed lead time), the idea of an evidence-based recommendation engine, and the numbered-script pipeline structure.

## Result of part 1

Everything non-analytical is gone. The remaining project is Python + pandas + NumPy + SQLite + matplotlib/seaborn. The original code remains available in the git history (`git log`, `git show <old commit>:backend/app/...`).

---

# Part 2 - Migration from synthetic to real data (Kaggle M5, Walmart)

**Why:** findings on a self-generated dataset mostly show what the generator was told to do, which weakens the project in an interview. The whole analysis was re-run on the real Kaggle *M5 Forecasting - Accuracy* data.

**What changed**

| Area | Synthetic version | Real-data version |
|---|---|---|
| Data | 90 SKUs x 5 warehouses x 728 days, generated (`datagen.py`), with injected dirt | 3,049 items x 10 stores x 1,913 days (273 full weeks), real, downloaded by the user |
| Cleaning | removed duplicates, sign errors, typos, mixed dates (all injected) | validates structure, masks pre-launch zeros (no price = not on sale), flags price jumps and spikes; the real data had none of the injected problems |
| KPIs | fill rate, stock-outs, turnover, days of inventory, lead times, suppliers, freight | **Dropped** - M5 has no stock, cost or supplier data. Replaced by revenue, ABC, demand CV / intermittency / demand class, price-cut, SNAP, event, weekday and seasonality analysis |
| Safety stock / reorder point | from simulated lead times | **Assumption-based** (assumed 1-week lead time, in `config.py`), labelled everywhere |
| Forecasting | weekly SKU demand, promo flag feature | weekly item x state demand, price ratio / SNAP / event features; same evaluation discipline |
| Stock-out cost story | $ lost revenue | not claimable - removed rather than faked |

**What was verified**
- Units and revenue were recomputed independently from the raw files for every store (`src/verify_against_raw.py`): units identical, revenue identical to the cent.
- Daily and weekly aggregates reconcile (units and revenue); SQL KPIs match pandas (tests).
- A forecasting leakage review: scaling, standardisation and the outlier cap use train statistics only; baselines are tuned on dev only; ABC for error analysis uses train revenue only; the test set is used once.

**Bug found and fixed during the migration:** daily revenue was accumulated in float32 and was $44 below the weekly total on $187M; it is now accumulated in float64 with prices rounded to cents so the tables tie exactly.

**Honest limits:** the real data cannot support service-level conclusions; the project says so instead of simulating them as findings.
