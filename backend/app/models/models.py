from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, Date, DateTime, ForeignKey, Text, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="analyst")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    supplier_code = Column(String(20), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    country = Column(String(100), nullable=False)
    region = Column(String(100), nullable=False, index=True)
    category = Column(String(100), nullable=False)
    risk_tier = Column(String(20), default="medium", index=True)
    on_time_rate = Column(Numeric(5, 4))
    quality_score = Column(Numeric(5, 2))
    avg_lead_time_days = Column(Numeric(6, 2))
    lead_time_std_days = Column(Numeric(6, 2))
    cost_index = Column(Numeric(6, 3), default=1.0)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    products = relationship("Product", back_populates="primary_supplier")


class Warehouse(Base):
    __tablename__ = "warehouses"
    id = Column(Integer, primary_key=True)
    warehouse_code = Column(String(20), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    region = Column(String(100), nullable=False)
    capacity_units = Column(Integer, nullable=False)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    sku = Column(String(30), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False, index=True)
    unit_cost = Column(Numeric(10, 2), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    primary_supplier_id = Column(Integer, ForeignKey("suppliers.id"), index=True)
    abc_class = Column(String(1))
    safety_stock_units = Column(Integer, default=0)
    reorder_point_units = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    primary_supplier = relationship("Supplier", back_populates="products")


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"))
    snapshot_date = Column(Date, index=True)
    on_hand_units = Column(Integer, nullable=False)
    in_transit_units = Column(Integer, default=0)
    allocated_units = Column(Integer, default=0)
    stockout_flag = Column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("product_id", "warehouse_id", "snapshot_date"),)


class DemandHistory(Base):
    __tablename__ = "demand_history"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"))
    demand_date = Column(Date, index=True)
    units_demanded = Column(Integer, nullable=False)
    units_fulfilled = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("product_id", "warehouse_id", "demand_date"),)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id = Column(Integer, primary_key=True)
    po_number = Column(String(30), unique=True, nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"))
    order_date = Column(Date, index=True)
    promised_date = Column(Date, nullable=False)
    actual_delivery_date = Column(Date)
    status = Column(String(20), default="open", index=True)
    total_cost = Column(Numeric(12, 2), default=0)
    created_at = Column(DateTime, server_default=func.now())

    items = relationship("PurchaseOrderItem", back_populates="purchase_order")
    shipments = relationship("Shipment", back_populates="purchase_order")


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    id = Column(Integer, primary_key=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    quantity = Column(Integer, nullable=False)
    unit_cost = Column(Numeric(10, 2), nullable=False)
    quantity_received = Column(Integer, default=0)
    defect_units = Column(Integer, default=0)

    purchase_order = relationship("PurchaseOrder", back_populates="items")


class Shipment(Base):
    __tablename__ = "shipments"
    id = Column(Integer, primary_key=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), index=True)
    carrier = Column(String(100), nullable=False)
    ship_date = Column(Date, nullable=False)
    expected_arrival = Column(Date, nullable=False)
    actual_arrival = Column(Date)
    mode = Column(String(20), default="ocean")
    status = Column(String(20), default="in_transit", index=True)
    delay_days = Column(Integer, default=0)
    freight_cost = Column(Numeric(10, 2), default=0)

    purchase_order = relationship("PurchaseOrder", back_populates="shipments")


class QualityRecord(Base):
    __tablename__ = "quality_records"
    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    inspection_date = Column(Date, index=True)
    units_inspected = Column(Integer, nullable=False)
    units_defective = Column(Integer, nullable=False)
    defect_rate = Column(Numeric(6, 4), nullable=False)
    root_cause = Column(String(255))


class CustomerOrder(Base):
    __tablename__ = "customer_orders"
    id = Column(Integer, primary_key=True)
    order_number = Column(String(30), unique=True, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"))
    order_date = Column(Date, index=True)
    requested_qty = Column(Integer, nullable=False)
    shipped_qty = Column(Integer, default=0)
    promised_date = Column(Date, nullable=False)
    shipped_date = Column(Date)
    on_time = Column(Boolean)
    in_full = Column(Boolean)


class MLRun(Base):
    __tablename__ = "ml_runs"
    id = Column(Integer, primary_key=True)
    model_name = Column(String(100), nullable=False)
    run_at = Column(DateTime, server_default=func.now())
    metrics_json = Column(JSON)
    notes = Column(Text)


class StockoutRiskScore(Base):
    __tablename__ = "stockout_risk_scores"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"))
    as_of_date = Column(Date, index=True)
    risk_probability = Column(Numeric(6, 4), nullable=False)
    risk_level = Column(String(20), index=True)
    days_of_supply = Column(Numeric(8, 2))
    explanation_json = Column(JSON)
    __table_args__ = (UniqueConstraint("product_id", "warehouse_id", "as_of_date"),)


class Anomaly(Base):
    __tablename__ = "anomalies"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(Integer, nullable=False)
    metric_name = Column(String(100), nullable=False)
    detected_date = Column(Date, index=True)
    metric_value = Column(Numeric(12, 4))
    expected_range_low = Column(Numeric(12, 4))
    expected_range_high = Column(Numeric(12, 4))
    anomaly_score = Column(Numeric(8, 4))
    severity = Column(String(20))
    description = Column(Text)


class DemandForecast(Base):
    __tablename__ = "demand_forecasts"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"))
    forecast_date = Column(Date, index=True)
    forecast_units = Column(Numeric(10, 2), nullable=False)
    lower_bound = Column(Numeric(10, 2), nullable=False)
    upper_bound = Column(Numeric(10, 2), nullable=False)
    model_name = Column(String(50), default="random_forest")
    generated_at = Column(DateTime, server_default=func.now())
    __table_args__ = (UniqueConstraint("product_id", "warehouse_id", "forecast_date", "model_name"),)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id = Column(Integer, primary_key=True)
    category = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(30))
    entity_id = Column(Integer)
    priority = Column(String(20), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    estimated_impact = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    resolved = Column(Boolean, default=False)
