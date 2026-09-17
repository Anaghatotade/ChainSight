from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user

router = APIRouter(prefix="/api/v1/anomalies", tags=["anomalies"])


@router.get("")
def list_anomalies(
    entity_type: str | None = Query(None, description="product|supplier"),
    severity: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), _=Depends(get_current_user),
):
    base_filter = "WHERE 1=1"
    params = {}
    if entity_type:
        base_filter += " AND a.entity_type = :et"
        params["et"] = entity_type
    if severity:
        base_filter += " AND a.severity = :sev"
        params["sev"] = severity

    total = db.execute(text(f"SELECT COUNT(*) FROM anomalies a {base_filter}"), params).scalar() or 0

    query = f"""
        SELECT a.id, a.entity_type, a.entity_id, a.metric_name, a.detected_date, a.metric_value,
               a.expected_range_low, a.expected_range_high, a.anomaly_score, a.severity, a.description,
               CASE WHEN a.entity_type = 'product' THEN p.name
                    WHEN a.entity_type = 'supplier' THEN s.name END AS entity_name
        FROM anomalies a
        LEFT JOIN products p ON a.entity_type = 'product' AND p.id = a.entity_id
        LEFT JOIN suppliers s ON a.entity_type = 'supplier' AND s.id = a.entity_id
        {base_filter}
        ORDER BY a.detected_date DESC, a.anomaly_score DESC
        LIMIT :lim OFFSET :off
    """
    params["lim"] = limit
    params["off"] = offset

    rows = db.execute(text(query), params).mappings().all()
    return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/summary")
def anomaly_summary(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT entity_type, severity, COUNT(*) AS count
        FROM anomalies GROUP BY entity_type, severity ORDER BY entity_type, severity
    """)).mappings().all()
    return [dict(r) for r in rows]
