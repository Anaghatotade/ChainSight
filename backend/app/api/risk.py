from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.schemas import schemas as sch

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])


@router.get("/stockout")
def stockout_risk(
    risk_level: str | None = Query(None, description="low|medium|high|critical"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), _=Depends(get_current_user),
):
    base_filter = "WHERE 1=1"
    params = {}
    if risk_level:
        base_filter += " AND r.risk_level = :rl"
        params["rl"] = risk_level

    total = db.execute(text(f"SELECT COUNT(*) FROM stockout_risk_scores r {base_filter}"), params).scalar() or 0

    query = f"""
        SELECT r.product_id, p.sku, p.name AS product_name, r.warehouse_id, r.risk_probability,
               r.risk_level, r.days_of_supply, r.explanation_json,
               i.on_hand_units, s.name AS supplier_name,
               COALESCE(d.avg_daily_demand, 0) AS avg_daily_demand
        FROM stockout_risk_scores r
        JOIN products p ON p.id = r.product_id
        LEFT JOIN suppliers s ON s.id = p.primary_supplier_id
        LEFT JOIN inventory_snapshots i ON i.product_id = r.product_id AND i.warehouse_id = r.warehouse_id
             AND i.snapshot_date = r.as_of_date
        LEFT JOIN (
            SELECT product_id, warehouse_id, AVG(units_demanded) AS avg_daily_demand
            FROM demand_history
            WHERE demand_date >= (SELECT MAX(demand_date) FROM demand_history) - INTERVAL '30 days'
            GROUP BY product_id, warehouse_id
        ) d ON d.product_id = r.product_id AND d.warehouse_id = r.warehouse_id
        {base_filter}
        ORDER BY r.risk_probability DESC
        LIMIT :lim OFFSET :off
    """
    params["lim"] = limit
    params["off"] = offset

    rows = db.execute(text(query), params).mappings().all()
    items = []
    for r in rows:
        explanation = r["explanation_json"] or []
        items.append(sch.StockoutRiskOut(
            product_id=r["product_id"], sku=r["sku"], product_name=r["product_name"],
            warehouse_id=r["warehouse_id"], risk_probability=float(r["risk_probability"]),
            risk_level=r["risk_level"], days_of_supply=float(r["days_of_supply"] or 0),
            on_hand_units=int(r["on_hand_units"] or 0), avg_daily_demand=float(r["avg_daily_demand"] or 0),
            supplier_name=r["supplier_name"],
            explanation=[sch.RiskExplanationFactor(**f) for f in explanation],
        ))
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/summary")
def risk_summary(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT risk_level, COUNT(*) AS count FROM stockout_risk_scores GROUP BY risk_level
    """)).mappings().all()
    return [dict(r) for r in rows]
