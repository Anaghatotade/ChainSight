#!/bin/bash
set -e

echo "Waiting for Postgres..."
python - <<'EOF'
import time
import sqlalchemy
from app.core.config import settings

for i in range(60):
    try:
        engine = sqlalchemy.create_engine(settings.DATABASE_URL)
        conn = engine.connect()
        conn.close()
        print("Postgres is ready.")
        break
    except Exception as e:
        print(f"Waiting for Postgres... ({i+1}/60) {e}")
        time.sleep(2)
else:
    raise SystemExit("Postgres did not become ready in time")
EOF

SEED_FLAG_TABLE_CHECK=$(python - <<'EOF'
import sqlalchemy
from app.core.config import settings
try:
    engine = sqlalchemy.create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(sqlalchemy.text(
            "SELECT to_regclass('public.suppliers') IS NOT NULL AND "
            "(SELECT COUNT(*) FROM suppliers) > 0"
        )).scalar()
        print("yes" if result else "no")
except Exception:
    print("no")
EOF
)

if [ "$SEED_FLAG_TABLE_CHECK" = "yes" ] && [ "$FORCE_RESEED" != "true" ]; then
    echo "Database already seeded. Skipping ETL generation (set FORCE_RESEED=true to regenerate)."
else
    echo "Generating synthetic supply chain dataset (this may take 1-3 minutes)..."
    python -m app.etl.generate_synthetic_data
    echo "Seeding demo users..."
    python -m app.etl.seed_users
    echo "Running analytics/ML pipeline (risk scoring, anomaly detection, forecasting, recommendations)..."
    python -m app.ml.pipeline
fi

echo "Ensuring demo users exist..."
python -m app.etl.seed_users || true

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
