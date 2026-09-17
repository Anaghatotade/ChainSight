import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import models as m
from app.schemas import schemas as sch
from app.ml import forecasting

router = APIRouter(prefix="/api/v1/forecasting", tags=["forecasting"])


@router.get("/accuracy/summary")
def forecast_accuracy_summary(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Aggregate backtest accuracy sampled across a subset of SKUs (computed live, capped for latency)."""
    pairs = db.execute(text("""
        SELECT DISTINCT product_id, warehouse_id FROM demand_history LIMIT 15
    """)).all()
    maes, mapes = [], []
    for pid, wid in pairs:
        hist_rows = db.execute(text("""
            SELECT demand_date AS ds, units_demanded AS y FROM demand_history
            WHERE product_id = :p AND warehouse_id = :w ORDER BY demand_date
        """), {"p": pid, "w": wid}).mappings().all()
        hist_df = pd.DataFrame(hist_rows)
        if len(hist_df) < 60:
            continue
        _, metrics = forecasting.train_and_forecast(hist_df, horizon_days=14, backtest_days=14)
        if metrics.get("mae") is not None:
            maes.append(metrics["mae"])
            mapes.append(metrics["mape"])
    return {
        "sample_size": len(maes),
        "avg_mae": round(sum(maes) / len(maes), 2) if maes else None,
        "avg_mape": round(sum(mapes) / len(mapes), 2) if mapes else None,
    }


@router.get("/{product_id}/{warehouse_id}", response_model=sch.ForecastResponse)
def get_forecast(product_id: int, warehouse_id: int, live: bool = False,
                  db: Session = Depends(get_db), _=Depends(get_current_user)):
    product = db.query(m.Product).filter(m.Product.id == product_id).first()
    if not product:
        raise HTTPException(404, "Product not found")

    hist_rows = db.execute(text("""
        SELECT demand_date AS ds, units_demanded AS y FROM demand_history
        WHERE product_id = :p AND warehouse_id = :w ORDER BY demand_date
    """), {"p": product_id, "w": warehouse_id}).mappings().all()
    hist_df = pd.DataFrame(hist_rows)
    if hist_df.empty:
        raise HTTPException(404, "No demand history for this product/warehouse")

    history = [sch.ForecastPoint(date=r["ds"], forecast_units=r["y"], lower_bound=r["y"], upper_bound=r["y"],
                                  actual_units=r["y"]) for r in hist_rows[-90:]]

    if live:
        forecast_df, metrics = forecasting.train_and_forecast(hist_df, horizon_days=30)
        forecast = [sch.ForecastPoint(date=r["ds"], forecast_units=round(r["yhat"], 1),
                                       lower_bound=round(r["yhat_lower"], 1), upper_bound=round(r["yhat_upper"], 1))
                    for _, r in forecast_df.iterrows()]
        return sch.ForecastResponse(product_id=product_id, sku=product.sku, warehouse_id=warehouse_id,
                                     model_name=metrics["model"], history=history, forecast=forecast,
                                     mae=metrics.get("mae"), mape=metrics.get("mape"))

    stored = db.execute(text("""
        SELECT forecast_date AS ds, forecast_units, lower_bound, upper_bound, model_name
        FROM demand_forecasts WHERE product_id = :p AND warehouse_id = :w ORDER BY forecast_date
    """), {"p": product_id, "w": warehouse_id}).mappings().all()

    if not stored:
        forecast_df, metrics = forecasting.train_and_forecast(hist_df, horizon_days=30)
        forecast = [sch.ForecastPoint(date=r["ds"], forecast_units=round(r["yhat"], 1),
                                       lower_bound=round(r["yhat_lower"], 1), upper_bound=round(r["yhat_upper"], 1))
                    for _, r in forecast_df.iterrows()]
        model_name = metrics["model"]
        mae, mape = metrics.get("mae"), metrics.get("mape")
    else:
        forecast = [sch.ForecastPoint(date=r["ds"], forecast_units=float(r["forecast_units"]),
                                       lower_bound=float(r["lower_bound"]), upper_bound=float(r["upper_bound"]))
                    for r in stored]
        model_name = stored[0]["model_name"]
        mae, mape = None, None

    return sch.ForecastResponse(product_id=product_id, sku=product.sku, warehouse_id=warehouse_id,
                                 model_name=model_name, history=history, forecast=forecast, mae=mae, mape=mape)

