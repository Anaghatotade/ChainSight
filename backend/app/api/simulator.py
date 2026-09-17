from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import models as m
from app.schemas import schemas as sch
from app.services import simulator as sim_service

router = APIRouter(prefix="/api/v1/simulator", tags=["simulator"])


@router.post("/run", response_model=sch.SimulationResult)
def run_simulation(payload: sch.SimulationInput, db: Session = Depends(get_db), _=Depends(get_current_user)):
    product = db.query(m.Product).filter(m.Product.id == payload.product_id).first()
    if not product:
        raise HTTPException(404, "Product not found")
    supplier = db.query(m.Supplier).filter(m.Supplier.id == product.primary_supplier_id).first()

    stats = db.execute(text("""
        SELECT AVG(units_demanded) AS avg_demand, STDDEV(units_demanded) AS std_demand
        FROM demand_history WHERE product_id = :p AND warehouse_id = :w
        AND demand_date >= (SELECT MAX(demand_date) FROM demand_history) - INTERVAL '60 days'
    """), {"p": payload.product_id, "w": payload.warehouse_id}).mappings().first()

    warehouse = db.query(m.Warehouse).filter(m.Warehouse.id == payload.warehouse_id).first()

    avg_demand = float(stats["avg_demand"] or 5)
    std_demand = float(stats["std_demand"] or avg_demand * 0.3)
    lead_time_mean = float(supplier.avg_lead_time_days) if supplier else 14.0
    lead_time_std = float(supplier.lead_time_std_days) if supplier else 3.0

    result = sim_service.run_simulation(
        sku=product.sku, avg_demand=avg_demand, std_demand=std_demand,
        lead_time_mean=lead_time_mean, lead_time_std=lead_time_std,
        safety_stock=product.safety_stock_units, reorder_point=product.reorder_point_units,
        unit_cost=float(product.unit_cost), warehouse_capacity=warehouse.capacity_units if warehouse else 100000,
        demand_change_pct=payload.demand_change_pct, lead_time_change_days=payload.lead_time_change_days,
        supplier_capacity_change_pct=payload.supplier_capacity_change_pct,
        safety_stock_change_units=payload.safety_stock_change_units,
        cost_change_pct=payload.cost_change_pct, simulation_days=payload.simulation_days,
    )

    baseline_summary = {k: v for k, v in result["baseline"].items() if k != "timeline"}
    scenario_summary = {k: v for k, v in result["scenario"].items() if k != "timeline"}

    return sch.SimulationResult(
        product_id=product.id, sku=product.sku,
        baseline=baseline_summary, scenario=scenario_summary, delta=result["delta"],
        timeline_baseline=[sch.SimulationDayResult(**t) for t in result["baseline"]["timeline"]],
        timeline_scenario=[sch.SimulationDayResult(**t) for t in result["scenario"]["timeline"]],
        narrative=result["narrative"],
    )
