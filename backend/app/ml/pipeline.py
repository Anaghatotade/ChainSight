"""
ML / Analytics Pipeline
========================
Orchestrates the full analytics refresh:
  1. Build feature table from raw DB tables (pandas / SQL)
  2. Train + score the stockout-risk classifier (with explanations)
  3. Run anomaly detection across demand, supplier delay, and quality signals
  4. Train + generate demand forecasts per (product, warehouse)
  5. Synthesize actionable recommendations from all of the above
  6. Persist everything back to Postgres so API reads are fast

Run standalone:  python -m app.ml.pipeline
Also triggerable via POST /api/v1/admin/run-pipeline
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.core.database import engine, SessionLocal
from app.models import models as m
from app.ml import forecasting, anomaly_detection, risk_scoring
from app.services import supplier_scoring, inventory_analysis, recommendations as reco_service


def _load_frame(query: str) -> pd.DataFrame:
    return pd.read_sql(text(query), engine)


def build_risk_training_table() -> pd.DataFrame:
    inv = _load_frame("""
        SELECT i.product_id, i.warehouse_id, i.snapshot_date, i.on_hand_units, i.stockout_flag,
               p.safety_stock_units, p.reorder_point_units, p.primary_supplier_id,
               s.avg_lead_time_days, s.lead_time_std_days, s.on_time_rate, s.quality_score
        FROM inventory_snapshots i
        JOIN products p ON p.id = i.product_id
        LEFT JOIN suppliers s ON s.id = p.primary_supplier_id
        ORDER BY i.product_id, i.warehouse_id, i.snapshot_date
    """)
    dem = _load_frame("""
        SELECT product_id, warehouse_id, demand_date, units_demanded
        FROM demand_history ORDER BY product_id, warehouse_id, demand_date
    """)
    df = inv.merge(dem, left_on=["product_id", "warehouse_id", "snapshot_date"],
                    right_on=["product_id", "warehouse_id", "demand_date"], how="left")
    df["units_demanded"] = df["units_demanded"].fillna(0)

    frames = []
    for (pid, wid), g in df.groupby(["product_id", "warehouse_id"]):
        g = g.sort_values("snapshot_date").reset_index(drop=True)
        g["avg_daily_demand"] = g["units_demanded"].rolling(30, min_periods=7).mean()
        g["demand_std"] = g["units_demanded"].rolling(30, min_periods=7).std().fillna(0)
        g["recent_mean"] = g["units_demanded"].rolling(14, min_periods=5).mean()
        g["prior_mean"] = g["units_demanded"].shift(14).rolling(14, min_periods=5).mean()
        g["recent_trend_pct"] = ((g["recent_mean"] - g["prior_mean"]) / g["prior_mean"].replace(0, np.nan)).fillna(0)

        g["days_of_supply"] = g["on_hand_units"] / g["avg_daily_demand"].replace(0, np.nan)
        g["days_of_supply"] = g["days_of_supply"].fillna(g["on_hand_units"])
        g["demand_cv"] = (g["demand_std"] / g["avg_daily_demand"].replace(0, np.nan)).fillna(0)
        g["lead_time_days"] = g["avg_lead_time_days"].fillna(10)
        g["lead_time_cv"] = (g["lead_time_std_days"] / g["avg_lead_time_days"].replace(0, np.nan)).fillna(0.2)
        g["supplier_on_time_rate"] = g["on_time_rate"].fillna(0.85)
        g["defect_rate"] = ((100 - g["quality_score"].fillna(95)) / 1000).clip(0, 0.3)
        g["safety_stock_ratio"] = (g["safety_stock_units"] /
                                    (g["avg_daily_demand"].replace(0, np.nan) * g["lead_time_days"] + 1e-6)).fillna(1.0)

        # forward-looking label: any stockout in the next 14 days
        reversed_flag = g["stockout_flag"].iloc[::-1]
        forward_any = reversed_flag.rolling(14, min_periods=1).max().iloc[::-1]
        g["label"] = forward_any.shift(-1).fillna(0).astype(int)

        frames.append(g)

    result = pd.concat(frames, ignore_index=True)
    return result.dropna(subset=["avg_daily_demand"])


def run_risk_scoring(session):
    print("[pipeline] Building risk training table...")
    train_df = build_risk_training_table()
    if train_df.empty:
        print("[pipeline] No data for risk model, skipping.")
        return pd.DataFrame()

    bundle = risk_scoring.train_risk_model(train_df)

    latest_date = train_df["snapshot_date"].max()
    latest = train_df[train_df["snapshot_date"] == latest_date].copy()

    product_lookup = {p.id: p for p in session.query(m.Product).all()}
    supplier_lookup = {s.id: s for s in session.query(m.Supplier).all()}

    session.query(m.StockoutRiskScore).delete()
    results = []
    for _, row in latest.iterrows():
        feature_row = {f: row[f] for f in risk_scoring.FEATURES}
        proba, factors = risk_scoring.score_instance(bundle, feature_row)
        level = risk_scoring.risk_level_from_probability(proba)
        product = product_lookup.get(int(row["product_id"]))
        supplier = supplier_lookup.get(int(row["primary_supplier_id"])) if pd.notna(row["primary_supplier_id"]) else None

        session.add(m.StockoutRiskScore(
            product_id=int(row["product_id"]), warehouse_id=int(row["warehouse_id"]),
            as_of_date=latest_date, risk_probability=round(proba, 4), risk_level=level,
            days_of_supply=round(float(row["days_of_supply"]), 2),
            explanation_json=factors,
        ))
        results.append(dict(
            product_id=int(row["product_id"]), warehouse_id=int(row["warehouse_id"]),
            sku=product.sku if product else "?", name=product.name if product else "?",
            risk_probability=proba, risk_level=level,
            days_of_supply=float(row["days_of_supply"]),
            on_hand_units=int(row["on_hand_units"]), avg_daily_demand=float(row["avg_daily_demand"]),
            supplier_name=supplier.name if supplier else None,
            explanation=factors,
        ))
    session.commit()
    print(f"[pipeline] Stored {len(results)} stockout risk scores.")
    return pd.DataFrame(results)


def run_anomaly_detection(session):
    print("[pipeline] Running anomaly detection...")
    session.query(m.Anomaly).delete()
    session.commit()

    all_anomalies = []

    demand = _load_frame("""
        SELECT product_id, demand_date, SUM(units_demanded) AS units_demanded
        FROM demand_history GROUP BY product_id, demand_date ORDER BY product_id, demand_date
    """)
    for pid, g in demand.groupby("product_id"):
        anomalies = anomaly_detection.detect_demand_anomalies(g.rename(columns={"units_demanded": "units_demanded"}), pid)
        all_anomalies.extend(anomalies)

    po = _load_frame("""
        SELECT supplier_id, order_date,
               (actual_delivery_date - promised_date) AS delay_days
        FROM purchase_orders WHERE actual_delivery_date IS NOT NULL
        ORDER BY supplier_id, order_date
    """)
    suppliers = {s.id: s.name for s in session.query(m.Supplier).all()}
    for sid, g in po.groupby("supplier_id"):
        anomalies = anomaly_detection.detect_supplier_delay_anomalies(g, sid, suppliers.get(sid, f"Supplier {sid}"))
        all_anomalies.extend(anomalies)

    quality = _load_frame("""
        SELECT supplier_id, inspection_date, defect_rate
        FROM quality_records ORDER BY supplier_id, inspection_date
    """)
    for sid, g in quality.groupby("supplier_id"):
        anomalies = anomaly_detection.detect_quality_anomalies(g, sid, suppliers.get(sid, f"Supplier {sid}"))
        all_anomalies.extend(anomalies)

    # keep most recent + highest severity anomalies to a reasonable count
    all_anomalies.sort(key=lambda a: (a["detected_date"], a["anomaly_score"]), reverse=True)
    trimmed = all_anomalies[:400]

    for a in trimmed:
        session.add(m.Anomaly(**a))
    session.commit()
    print(f"[pipeline] Stored {len(trimmed)} anomalies (of {len(all_anomalies)} detected).")
    return trimmed


def run_forecasting(session):
    print("[pipeline] Generating demand forecasts...")
    session.query(m.DemandForecast).delete()
    session.commit()

    demand = _load_frame("""
        SELECT product_id, warehouse_id, demand_date, units_demanded
        FROM demand_history ORDER BY product_id, warehouse_id, demand_date
    """)
    count = 0
    for (pid, wid), g in demand.groupby(["product_id", "warehouse_id"]):
        hist = g.rename(columns={"demand_date": "ds", "units_demanded": "y"})[["ds", "y"]]
        forecast_df, metrics = forecasting.train_and_forecast(hist, horizon_days=30)
        for _, row in forecast_df.iterrows():
            session.add(m.DemandForecast(
                product_id=int(pid), warehouse_id=int(wid), forecast_date=row["ds"],
                forecast_units=round(float(row["yhat"]), 2),
                lower_bound=round(float(row["yhat_lower"]), 2),
                upper_bound=round(float(row["yhat_upper"]), 2),
                model_name=metrics["model"],
            ))
        count += 1
        if count % 40 == 0:
            session.commit()
            print(f"[pipeline]   forecasted {count} product-warehouse series...")
    session.commit()
    print(f"[pipeline] Forecasted {count} product-warehouse series.")


def run_recommendations(session, risk_df):
    print("[pipeline] Generating recommendations...")
    session.query(m.Recommendation).delete()
    session.commit()

    perf = _load_frame("""
        SELECT s.id AS supplier_id, s.name, s.region, s.category, s.on_time_rate,
               s.cost_index, s.lead_time_std_days,
               COALESCE(AVG(qr.defect_rate), 0.02) AS avg_defect_rate
        FROM suppliers s
        LEFT JOIN quality_records qr ON qr.supplier_id = s.id
        GROUP BY s.id, s.name, s.region, s.category, s.on_time_rate, s.cost_index, s.lead_time_std_days
    """)
    supplier_scores_df = supplier_scoring.score_suppliers(perf)

    latest_date = _load_frame("SELECT MAX(snapshot_date) AS d FROM inventory_snapshots")["d"].iloc[0]
    inv = _load_frame(f"""
        SELECT i.product_id, i.warehouse_id, i.on_hand_units, i.in_transit_units,
               p.sku, p.name, p.category, p.abc_class, p.safety_stock_units, p.reorder_point_units
        FROM inventory_snapshots i JOIN products p ON p.id = i.product_id
        WHERE i.snapshot_date = '{latest_date}'
    """)
    avg_dem = _load_frame("""
        SELECT product_id, warehouse_id, AVG(units_demanded) AS avg_daily_demand
        FROM demand_history
        WHERE demand_date >= (SELECT MAX(demand_date) FROM demand_history) - INTERVAL '30 days'
        GROUP BY product_id, warehouse_id
    """)
    inventory_df = inventory_analysis.compute_inventory_health(inv, avg_dem)

    anomalies_raw = _load_frame("SELECT * FROM anomalies").to_dict("records")

    if risk_df is None or risk_df.empty:
        risk_df = pd.DataFrame(columns=["product_id", "sku", "risk_probability", "risk_level", "explanation"])

    recs = reco_service.generate_recommendations(supplier_scores_df, inventory_df, risk_df, anomalies_raw)
    for r in recs:
        session.add(m.Recommendation(**r))
    session.commit()
    print(f"[pipeline] Stored {len(recs)} recommendations.")


def run_full_pipeline():
    session = SessionLocal()
    try:
        risk_df = run_risk_scoring(session)
        run_anomaly_detection(session)
        run_forecasting(session)
        run_recommendations(session, risk_df)
        session.add(m.MLRun(model_name="full_pipeline", metrics_json={"status": "success"}))
        session.commit()
        print("[pipeline] Full analytics pipeline complete.")
    finally:
        session.close()


if __name__ == "__main__":
    run_full_pipeline()
