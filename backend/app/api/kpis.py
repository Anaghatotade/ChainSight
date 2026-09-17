from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import models as m
from app.schemas import schemas as sch

router = APIRouter(prefix="/api/v1/kpis", tags=["kpis"])


@router.get("/summary", response_model=sch.KPISummary)
def kpi_summary(db: Session = Depends(get_db), _=Depends(get_current_user)):
    latest_date = db.execute(text("SELECT MAX(snapshot_date) FROM inventory_snapshots")).scalar()

    total_skus = db.execute(text("SELECT COUNT(*) FROM products WHERE active = TRUE")).scalar() or 0

    inv_value = db.execute(text("""
        SELECT COALESCE(SUM(i.on_hand_units * p.unit_cost), 0)
        FROM inventory_snapshots i JOIN products p ON p.id = i.product_id
        WHERE i.snapshot_date = :d
    """), {"d": latest_date}).scalar() or 0

    # inventory turnover ~ COGS (annualized fulfilled units * cost) / avg inventory value
    turnover = db.execute(text("""
        WITH cogs AS (
          SELECT SUM(d.units_fulfilled * p.unit_cost) AS total_cogs
          FROM demand_history d JOIN products p ON p.id = d.product_id
        ),
        avg_inv AS (
          SELECT AVG(i.on_hand_units * p.unit_cost) AS avg_value
          FROM inventory_snapshots i JOIN products p ON p.id = i.product_id
        )
        SELECT CASE WHEN avg_inv.avg_value > 0 THEN cogs.total_cogs / avg_inv.avg_value ELSE 0 END
        FROM cogs, avg_inv
    """)).scalar() or 0

    fill_rate = db.execute(text("""
        SELECT CASE WHEN SUM(units_demanded) > 0
               THEN SUM(units_fulfilled)::float / SUM(units_demanded) ELSE 1 END
        FROM demand_history
    """)).scalar() or 0

    otif = db.execute(text("""
        SELECT AVG(CASE WHEN on_time AND in_full THEN 1.0 ELSE 0.0 END) FROM customer_orders
    """)).scalar() or 0

    avg_lead_time = db.execute(text("SELECT AVG(avg_lead_time_days) FROM suppliers WHERE active = TRUE")).scalar() or 0

    open_pos = db.execute(text("SELECT COUNT(*) FROM purchase_orders WHERE status IN ('open','in_transit')")).scalar() or 0

    at_risk = db.execute(text("""
        SELECT COUNT(DISTINCT product_id) FROM stockout_risk_scores WHERE risk_level IN ('high','critical')
    """)).scalar() or 0

    anomalies_30d = db.execute(text("""
        SELECT COUNT(*) FROM anomalies WHERE detected_date >= (CURRENT_DATE - INTERVAL '30 days')
    """)).scalar() or 0

    avg_supplier_on_time = db.execute(text("SELECT AVG(on_time_rate) FROM suppliers WHERE active = TRUE")).scalar() or 0
    avg_defect = db.execute(text("SELECT AVG(defect_rate) FROM quality_records")).scalar() or 0
    # crude blended supplier score for the KPI tile (full scorecard lives in /suppliers/scores)
    avg_supplier_score = float(avg_supplier_on_time or 0) * 70 + (1 - float(avg_defect or 0)) * 30

    return sch.KPISummary(
        total_skus=total_skus,
        total_on_hand_value=round(float(inv_value), 2),
        avg_inventory_turnover=round(float(turnover), 2),
        fill_rate=round(float(fill_rate), 4),
        otif_rate=round(float(otif), 4),
        avg_lead_time_days=round(float(avg_lead_time), 2),
        open_pos=open_pos,
        at_risk_skus=at_risk,
        total_anomalies_30d=anomalies_30d,
        avg_supplier_score=round(avg_supplier_score, 1),
    )


@router.get("/trends/inventory-value")
def inventory_value_trend(days: int = 90, db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT i.snapshot_date AS date, SUM(i.on_hand_units * p.unit_cost) AS value
        FROM inventory_snapshots i JOIN products p ON p.id = i.product_id
        WHERE i.snapshot_date >= (SELECT MAX(snapshot_date) FROM inventory_snapshots) - (:days || ' days')::interval
        GROUP BY i.snapshot_date ORDER BY i.snapshot_date
    """), {"days": days}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/trends/fill-rate")
def fill_rate_trend(days: int = 90, db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT demand_date AS date,
               CASE WHEN SUM(units_demanded) > 0 THEN SUM(units_fulfilled)::float / SUM(units_demanded) ELSE 1 END AS fill_rate
        FROM demand_history
        WHERE demand_date >= (SELECT MAX(demand_date) FROM demand_history) - (:days || ' days')::interval
        GROUP BY demand_date ORDER BY demand_date
    """), {"days": days}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/trends/otif-by-category")
def otif_by_category(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT p.category, AVG(CASE WHEN co.on_time AND co.in_full THEN 1.0 ELSE 0.0 END) AS otif_rate,
               COUNT(*) AS order_count
        FROM customer_orders co JOIN products p ON p.id = co.product_id
        GROUP BY p.category ORDER BY otif_rate ASC
    """)).mappings().all()
    return [dict(r) for r in rows]
