from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import models as m
from app.schemas import schemas as sch

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


@router.get("/products", response_model=list[sch.ProductOut])
def list_products(category: str | None = None, db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(m.Product).filter(m.Product.active == True)  # noqa: E712
    if category:
        q = q.filter(m.Product.category == category)
    return q.order_by(m.Product.sku).all()


@router.get("/warehouses")
def list_warehouses(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.query(m.Warehouse).all()
    return [{"id": w.id, "warehouse_code": w.warehouse_code, "name": w.name,
             "region": w.region, "capacity_units": w.capacity_units} for w in rows]


@router.get("/categories")
def list_categories(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.query(m.Product.category).distinct().all()
    return sorted([r[0] for r in rows])


@router.get("/regions")
def list_regions(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.query(m.Supplier.region).distinct().all()
    return sorted([r[0] for r in rows])
