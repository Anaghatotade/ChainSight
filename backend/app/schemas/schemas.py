import email_validator
# Disable live DNS/MX deliverability checks: this is a self-contained demo app
# with locally-seeded accounts, and depending on the container having working
# outbound DNS at registration time is a fragile, unnecessary dependency
# (a common source of confusing failures on Docker Desktop / WSL2 setups).
# Format validation (RFC-compliant syntax) still applies.
email_validator.CHECK_DELIVERABILITY = False

from datetime import date, datetime
from typing import Optional, Any
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---------- Auth ----------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: str = "analyst"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Suppliers ----------
class SupplierOut(BaseModel):
    id: int
    supplier_code: str
    name: str
    country: str
    region: str
    category: str
    risk_tier: str
    on_time_rate: Optional[float] = None
    quality_score: Optional[float] = None
    avg_lead_time_days: Optional[float] = None
    lead_time_std_days: Optional[float] = None
    cost_index: Optional[float] = None
    active: bool

    class Config:
        from_attributes = True


class SupplierScore(BaseModel):
    supplier_id: int
    name: str
    region: str
    category: str
    on_time_rate: float
    avg_delay_days: float
    defect_rate: float
    cost_index: float
    lead_time_variability: float
    composite_score: float
    grade: str
    component_scores: dict[str, float]


# ---------- Products / Inventory ----------
class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    category: str
    unit_cost: float
    unit_price: float
    abc_class: Optional[str]
    safety_stock_units: int
    reorder_point_units: int

    class Config:
        from_attributes = True


class InventoryHealthOut(BaseModel):
    product_id: int
    sku: str
    name: str
    category: str
    abc_class: Optional[str]
    warehouse_id: int
    on_hand_units: int
    in_transit_units: int
    safety_stock_units: int
    reorder_point_units: int
    days_of_supply: Optional[float]
    avg_daily_demand: Optional[float]
    inventory_status: str  # healthy, low, critical, overstock


# ---------- KPIs ----------
class KPISummary(BaseModel):
    total_skus: int
    total_on_hand_value: float
    avg_inventory_turnover: float
    fill_rate: float
    otif_rate: float
    avg_lead_time_days: float
    open_pos: int
    at_risk_skus: int
    total_anomalies_30d: int
    avg_supplier_score: float


# ---------- Forecasting ----------
class ForecastPoint(BaseModel):
    date: date
    forecast_units: float
    lower_bound: float
    upper_bound: float
    actual_units: Optional[float] = None


class ForecastResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    product_id: int
    sku: str
    warehouse_id: int
    model_name: str
    history: list[ForecastPoint]
    forecast: list[ForecastPoint]
    mae: Optional[float] = None
    mape: Optional[float] = None


# ---------- Anomalies ----------
class AnomalyOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    entity_name: Optional[str] = None
    metric_name: str
    detected_date: date
    metric_value: float
    expected_range_low: float
    expected_range_high: float
    anomaly_score: float
    severity: str
    description: str

    class Config:
        from_attributes = True


# ---------- Risk ----------
class RiskExplanationFactor(BaseModel):
    factor: str
    contribution: float
    direction: str  # increases_risk / decreases_risk
    detail: str


class StockoutRiskOut(BaseModel):
    product_id: int
    sku: str
    product_name: str
    warehouse_id: int
    risk_probability: float
    risk_level: str
    days_of_supply: float
    on_hand_units: int
    avg_daily_demand: float
    supplier_name: Optional[str]
    explanation: list[RiskExplanationFactor]


# ---------- What-if Simulator ----------
class SimulationInput(BaseModel):
    product_id: int
    warehouse_id: int
    demand_change_pct: float = 0.0          # e.g. +20 for +20%
    lead_time_change_days: float = 0.0      # e.g. +5 days
    supplier_capacity_change_pct: float = 0.0  # e.g. -10 for -10% capacity
    safety_stock_change_units: int = 0
    cost_change_pct: float = 0.0            # unit cost change
    simulation_days: int = 90


class SimulationDayResult(BaseModel):
    day: int
    date: date
    projected_on_hand: float
    projected_demand: float
    stockout: bool
    service_level: float


class SimulationResult(BaseModel):
    product_id: int
    sku: str
    baseline: dict[str, Any]
    scenario: dict[str, Any]
    delta: dict[str, Any]
    timeline_baseline: list[SimulationDayResult]
    timeline_scenario: list[SimulationDayResult]
    narrative: list[str]


# ---------- Recommendations ----------
class RecommendationOut(BaseModel):
    id: int
    category: str
    entity_type: Optional[str]
    entity_id: Optional[int]
    priority: str
    title: str
    description: str
    estimated_impact: Optional[str]
    created_at: datetime
    resolved: bool

    class Config:
        from_attributes = True
