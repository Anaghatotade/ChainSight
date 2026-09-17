import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.services import inventory_analysis

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


@router.get("/health")
def inventory_health(
    status: str | None = Query(None, description="filter: healthy|low|critical|overstock"),
    category: str | None = None,
    abc_class: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), _=Depends(get_current_user),
):
    latest_date = db.execute(text("SELECT MAX(snapshot_date) FROM inventory_snapshots")).scalar()
    inv = pd.read_sql(text("""
        SELECT i.product_id, i.warehouse_id, i.on_hand_units, i.in_transit_units,
               p.sku, p.name, p.category, p.abc_class, p.safety_stock_units, p.reorder_point_units,
               w.name AS warehouse_name
        FROM inventory_snapshots i
        JOIN products p ON p.id = i.product_id
        JOIN warehouses w ON w.id = i.warehouse_id
        WHERE i.snapshot_date = :d
    """), db.bind, params={"d": latest_date})

    avg_dem = pd.read_sql(text("""
        SELECT product_id, warehouse_id, AVG(units_demanded) AS avg_daily_demand
        FROM demand_history
        WHERE demand_date >= (SELECT MAX(demand_date) FROM demand_history) - INTERVAL '30 days'
        GROUP BY product_id, warehouse_id
    """), db.bind)

    df = inventory_analysis.compute_inventory_health(inv, avg_dem)

    if status:
        df = df[df["inventory_status"] == status]
    if category:
        df = df[df["category"] == category]
    if abc_class:
        df = df[df["abc_class"] == abc_class]

    df = df.sort_values("days_of_supply")
    total = len(df)
    page = df.iloc[offset: offset + limit]
    return {"items": page.to_dict("records"), "total": total, "limit": limit, "offset": offset}


@router.get("/abc-analysis")
def abc_analysis(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT p.abc_class,
               COUNT(*) AS sku_count,
               SUM(p.unit_price * COALESCE(d.total_fulfilled, 0)) AS revenue
        FROM products p
        LEFT JOIN (
            SELECT product_id, SUM(units_fulfilled) AS total_fulfilled
            FROM demand_history GROUP BY product_id
        ) d ON d.product_id = p.id
        GROUP BY p.abc_class ORDER BY p.abc_class
    """)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/turnover-by-category")
def turnover_by_category(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.execute(text("""
        WITH cogs AS (
          SELECT p.category, SUM(d.units_fulfilled * p.unit_cost) AS total_cogs
          FROM demand_history d JOIN products p ON p.id = d.product_id
          GROUP BY p.category
        ),
        avg_inv AS (
          SELECT p.category, AVG(i.on_hand_units * p.unit_cost) AS avg_value
          FROM inventory_snapshots i JOIN products p ON p.id = i.product_id
          GROUP BY p.category
        )
        SELECT c.category, CASE WHEN a.avg_value > 0 THEN c.total_cogs / a.avg_value ELSE 0 END AS turnover
        FROM cogs c JOIN avg_inv a ON a.category = c.category
        ORDER BY turnover DESC
    """)).mappings().all()
    return [dict(r) for r in rows]
