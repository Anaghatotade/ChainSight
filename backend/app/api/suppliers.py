import pandas as pd
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import models as m
from app.schemas import schemas as sch
from app.services import supplier_scoring

router = APIRouter(prefix="/api/v1/suppliers", tags=["suppliers"])


@router.get("", response_model=list[sch.SupplierOut])
def list_suppliers(region: str | None = None, category: str | None = None,
                    db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(m.Supplier)
    if region:
        q = q.filter(m.Supplier.region == region)
    if category:
        q = q.filter(m.Supplier.category == category)
    return q.order_by(m.Supplier.name).all()


@router.get("/scores", response_model=list[sch.SupplierScore])
def supplier_scores(db: Session = Depends(get_db), _=Depends(get_current_user)):
    perf = pd.read_sql(text("""
        SELECT s.id AS supplier_id, s.name, s.region, s.category, s.on_time_rate,
               s.cost_index, s.lead_time_std_days,
               COALESCE(AVG(qr.defect_rate), 0.02) AS avg_defect_rate,
               COALESCE(AVG(GREATEST(po.actual_delivery_date - po.promised_date, 0)), 0) AS avg_delay_days
        FROM suppliers s
        LEFT JOIN quality_records qr ON qr.supplier_id = s.id
        LEFT JOIN purchase_orders po ON po.supplier_id = s.id AND po.actual_delivery_date IS NOT NULL
        WHERE s.active = TRUE
        GROUP BY s.id, s.name, s.region, s.category, s.on_time_rate, s.cost_index, s.lead_time_std_days
    """), db.bind)

    if perf.empty:
        return []

    scored = supplier_scoring.score_suppliers(perf)
    out = []
    for _, r in scored.iterrows():
        out.append(sch.SupplierScore(
            supplier_id=int(r["supplier_id"]), name=r["name"], region=r["region"], category=r["category"],
            on_time_rate=round(float(r["on_time_rate"]), 4), avg_delay_days=round(float(r["avg_delay_days"]), 2),
            defect_rate=round(float(r["avg_defect_rate"]), 4), cost_index=round(float(r["cost_index"]), 3),
            lead_time_variability=round(float(r["lead_time_std_days"]), 2),
            composite_score=float(r["composite_score"]), grade=r["grade"],
            component_scores={
                "on_time": round(float(r["score_on_time"]), 1),
                "quality": round(float(r["score_quality"]), 1),
                "cost": round(float(r["score_cost"]), 1),
                "consistency": round(float(r["score_consistency"]), 1),
            },
        ))
    return sorted(out, key=lambda x: -x.composite_score)


@router.get("/{supplier_id}")
def supplier_detail(supplier_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    supplier = db.query(m.Supplier).filter(m.Supplier.id == supplier_id).first()
    if not supplier:
        return {"error": "not found"}

    po_history = db.execute(text("""
        SELECT po_number, order_date, promised_date, actual_delivery_date, status, total_cost
        FROM purchase_orders WHERE supplier_id = :sid ORDER BY order_date DESC LIMIT 25
    """), {"sid": supplier_id}).mappings().all()

    quality_history = db.execute(text("""
        SELECT inspection_date, units_inspected, units_defective, defect_rate, root_cause
        FROM quality_records WHERE supplier_id = :sid ORDER BY inspection_date DESC LIMIT 25
    """), {"sid": supplier_id}).mappings().all()

    products = db.query(m.Product).filter(m.Product.primary_supplier_id == supplier_id).all()

    return {
        "supplier": sch.SupplierOut.model_validate(supplier),
        "recent_purchase_orders": [dict(r) for r in po_history],
        "recent_quality_records": [dict(r) for r in quality_history],
        "products_supplied": [sch.ProductOut.model_validate(p) for p in products],
    }
