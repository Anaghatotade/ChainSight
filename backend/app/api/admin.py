from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import models as m
from app.ml.pipeline import run_full_pipeline

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/run-pipeline")
def trigger_pipeline(background_tasks: BackgroundTasks, current_user: m.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(403, "Only admin users can trigger the analytics pipeline")
    background_tasks.add_task(run_full_pipeline)
    return {"status": "started", "message": "Analytics pipeline (risk scoring, anomaly detection, forecasting, recommendations) is running in the background."}


@router.get("/pipeline-runs")
def pipeline_runs(db: Session = Depends(get_db), _=Depends(get_current_user)):
    runs = db.query(m.MLRun).order_by(m.MLRun.run_at.desc()).limit(10).all()
    return [{"id": r.id, "model_name": r.model_name, "run_at": r.run_at, "metrics": r.metrics_json} for r in runs]
