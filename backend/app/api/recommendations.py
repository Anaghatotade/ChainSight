from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import models as m
from app.schemas import schemas as sch

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


@router.get("")
def list_recommendations(
    category: str | None = None,
    priority: str | None = None,
    resolved: bool | None = False,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), _=Depends(get_current_user),
):
    q = db.query(m.Recommendation)
    if category:
        q = q.filter(m.Recommendation.category == category)
    if priority:
        q = q.filter(m.Recommendation.priority == priority)
    if resolved is not None:
        q = q.filter(m.Recommendation.resolved == resolved)

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    results = q.all()
    results.sort(key=lambda r: priority_order.get(r.priority, 4))

    total = len(results)
    page = results[offset: offset + limit]
    return {
        "items": [sch.RecommendationOut.model_validate(r) for r in page],
        "total": total, "limit": limit, "offset": offset,
    }


@router.patch("/{rec_id}/resolve", response_model=sch.RecommendationOut)
def resolve_recommendation(rec_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    rec = db.query(m.Recommendation).filter(m.Recommendation.id == rec_id).first()
    if not rec:
        return {"error": "not found"}
    rec.resolved = True
    db.commit()
    db.refresh(rec)
    return rec
