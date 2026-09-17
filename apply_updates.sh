#!/bin/bash
# =============================================================================
# apply_updates.sh
#
# Applies the following changes to an existing copy of the ChainSight project:
#   1. Fixes registration/login reliability (removes live DNS/MX lookup from
#      email validation, which depended on the container's outbound DNS).
#   2. Switches auth session storage from localStorage to sessionStorage, so
#      different accounts can be signed in simultaneously in different tabs.
#   3. Adds pagination (limit/offset/total) to the anomalies, stockout-risk,
#      inventory-health, and recommendations endpoints + matching UI controls.
#   4. Adds CSV export buttons on suppliers/inventory/anomalies/risk/
#      recommendations pages.
#   5. Adds a GitHub Actions CI workflow (backend tests, frontend build,
#      Docker image builds).
#   6. Patches next/axios to their latest secure versions within the same
#      major version, and forces out a vulnerable bundled postcss copy.
#
# Run this ONCE from the project root (the folder containing docker-compose.yml).
#
# On Windows: open Git Bash in the project folder and run:  bash apply_updates.sh
# On Mac/Linux:  cd supply-chain-platform && bash apply_updates.sh
#
# This OVERWRITES the files listed below with their final, tested versions.
# If you've made your own edits to any of these files, back them up first.
# =============================================================================
set -e

if [ ! -f "docker-compose.yml" ]; then
  echo "ERROR: run this script from the project root (the folder with docker-compose.yml in it)."
  exit 1
fi

echo "Creating .github/workflows directory (new in this update)..."
mkdir -p .github/workflows

echo "Writing backend/app/schemas/schemas.py ..."
mkdir -p "$(dirname 'backend/app/schemas/schemas.py')"
cat > 'backend/app/schemas/schemas.py' << 'CHAINSIGHT_APPLY_EOF'
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
CHAINSIGHT_APPLY_EOF

echo "Writing backend/app/api/anomalies.py ..."
mkdir -p "$(dirname 'backend/app/api/anomalies.py')"
cat > 'backend/app/api/anomalies.py' << 'CHAINSIGHT_APPLY_EOF'
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
CHAINSIGHT_APPLY_EOF

echo "Writing backend/app/api/risk.py ..."
mkdir -p "$(dirname 'backend/app/api/risk.py')"
cat > 'backend/app/api/risk.py' << 'CHAINSIGHT_APPLY_EOF'
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.schemas import schemas as sch

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])


@router.get("/stockout")
def stockout_risk(
    risk_level: str | None = Query(None, description="low|medium|high|critical"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), _=Depends(get_current_user),
):
    base_filter = "WHERE 1=1"
    params = {}
    if risk_level:
        base_filter += " AND r.risk_level = :rl"
        params["rl"] = risk_level

    total = db.execute(text(f"SELECT COUNT(*) FROM stockout_risk_scores r {base_filter}"), params).scalar() or 0

    query = f"""
        SELECT r.product_id, p.sku, p.name AS product_name, r.warehouse_id, r.risk_probability,
               r.risk_level, r.days_of_supply, r.explanation_json,
               i.on_hand_units, s.name AS supplier_name,
               COALESCE(d.avg_daily_demand, 0) AS avg_daily_demand
        FROM stockout_risk_scores r
        JOIN products p ON p.id = r.product_id
        LEFT JOIN suppliers s ON s.id = p.primary_supplier_id
        LEFT JOIN inventory_snapshots i ON i.product_id = r.product_id AND i.warehouse_id = r.warehouse_id
             AND i.snapshot_date = r.as_of_date
        LEFT JOIN (
            SELECT product_id, warehouse_id, AVG(units_demanded) AS avg_daily_demand
            FROM demand_history
            WHERE demand_date >= (SELECT MAX(demand_date) FROM demand_history) - INTERVAL '30 days'
            GROUP BY product_id, warehouse_id
        ) d ON d.product_id = r.product_id AND d.warehouse_id = r.warehouse_id
        {base_filter}
        ORDER BY r.risk_probability DESC
        LIMIT :lim OFFSET :off
    """
    params["lim"] = limit
    params["off"] = offset

    rows = db.execute(text(query), params).mappings().all()
    items = []
    for r in rows:
        explanation = r["explanation_json"] or []
        items.append(sch.StockoutRiskOut(
            product_id=r["product_id"], sku=r["sku"], product_name=r["product_name"],
            warehouse_id=r["warehouse_id"], risk_probability=float(r["risk_probability"]),
            risk_level=r["risk_level"], days_of_supply=float(r["days_of_supply"] or 0),
            on_hand_units=int(r["on_hand_units"] or 0), avg_daily_demand=float(r["avg_daily_demand"] or 0),
            supplier_name=r["supplier_name"],
            explanation=[sch.RiskExplanationFactor(**f) for f in explanation],
        ))
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/summary")
def risk_summary(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT risk_level, COUNT(*) AS count FROM stockout_risk_scores GROUP BY risk_level
    """)).mappings().all()
    return [dict(r) for r in rows]
CHAINSIGHT_APPLY_EOF

echo "Writing backend/app/api/inventory.py ..."
mkdir -p "$(dirname 'backend/app/api/inventory.py')"
cat > 'backend/app/api/inventory.py' << 'CHAINSIGHT_APPLY_EOF'
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
CHAINSIGHT_APPLY_EOF

echo "Writing backend/app/api/recommendations.py ..."
mkdir -p "$(dirname 'backend/app/api/recommendations.py')"
cat > 'backend/app/api/recommendations.py' << 'CHAINSIGHT_APPLY_EOF'
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
CHAINSIGHT_APPLY_EOF

echo "Writing frontend/lib/api.ts ..."
mkdir -p "$(dirname 'frontend/lib/api.ts')"
cat > 'frontend/lib/api.ts' << 'CHAINSIGHT_APPLY_EOF'
import axios from "axios";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_URL,
});

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = sessionStorage.getItem("chainsight_token");
    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (typeof window !== "undefined" && error?.response?.status === 401) {
      sessionStorage.removeItem("chainsight_token");
      sessionStorage.removeItem("chainsight_user");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
}

export interface KPISummary {
  total_skus: number;
  total_on_hand_value: number;
  avg_inventory_turnover: number;
  fill_rate: number;
  otif_rate: number;
  avg_lead_time_days: number;
  open_pos: number;
  at_risk_skus: number;
  total_anomalies_30d: number;
  avg_supplier_score: number;
}

export interface SupplierScore {
  supplier_id: number;
  name: string;
  region: string;
  category: string;
  on_time_rate: number;
  avg_delay_days: number;
  defect_rate: number;
  cost_index: number;
  lead_time_variability: number;
  composite_score: number;
  grade: string;
  component_scores: Record<string, number>;
}

export interface InventoryHealthRow {
  product_id: number;
  warehouse_id: number;
  sku: string;
  name: string;
  category: string;
  abc_class: string;
  on_hand_units: number;
  in_transit_units: number;
  safety_stock_units: number;
  reorder_point_units: number;
  avg_daily_demand: number;
  days_of_supply: number;
  inventory_status: string;
  warehouse_name: string;
}

export interface AnomalyRow {
  id: number;
  entity_type: string;
  entity_id: number;
  entity_name: string | null;
  metric_name: string;
  detected_date: string;
  metric_value: number;
  expected_range_low: number;
  expected_range_high: number;
  anomaly_score: number;
  severity: string;
  description: string;
}

export interface RiskExplanationFactor {
  factor: string;
  contribution: number;
  direction: string;
  detail: string;
}

export interface StockoutRisk {
  product_id: number;
  sku: string;
  product_name: string;
  warehouse_id: number;
  risk_probability: number;
  risk_level: string;
  days_of_supply: number;
  on_hand_units: number;
  avg_daily_demand: number;
  supplier_name: string | null;
  explanation: RiskExplanationFactor[];
}

export interface Recommendation {
  id: number;
  category: string;
  entity_type: string | null;
  entity_id: number | null;
  priority: string;
  title: string;
  description: string;
  estimated_impact: string | null;
  created_at: string;
  resolved: boolean;
}

export interface ForecastPoint {
  date: string;
  forecast_units: number;
  lower_bound: number;
  upper_bound: number;
  actual_units?: number | null;
}

export interface ForecastResponse {
  product_id: number;
  sku: string;
  warehouse_id: number;
  model_name: string;
  history: ForecastPoint[];
  forecast: ForecastPoint[];
  mae?: number | null;
  mape?: number | null;
}

export interface Product {
  id: number;
  sku: string;
  name: string;
  category: string;
  unit_cost: number;
  unit_price: number;
  abc_class: string | null;
  safety_stock_units: number;
  reorder_point_units: number;
}

export interface Warehouse {
  id: number;
  warehouse_code: string;
  name: string;
  region: string;
  capacity_units: number;
}

export interface SimulationInput {
  product_id: number;
  warehouse_id: number;
  demand_change_pct: number;
  lead_time_change_days: number;
  supplier_capacity_change_pct: number;
  safety_stock_change_units: number;
  cost_change_pct: number;
  simulation_days: number;
}

export interface SimulationResult {
  product_id: number;
  sku: string;
  baseline: Record<string, any>;
  scenario: Record<string, any>;
  delta: Record<string, any>;
  timeline_baseline: any[];
  timeline_scenario: any[];
  narrative: string[];
}
CHAINSIGHT_APPLY_EOF

echo "Writing frontend/lib/csvExport.ts ..."
mkdir -p "$(dirname 'frontend/lib/csvExport.ts')"
cat > 'frontend/lib/csvExport.ts' << 'CHAINSIGHT_APPLY_EOF'
/**
 * Client-side CSV export: converts an array of flat objects into a CSV file
 * and triggers a browser download. No backend involvement needed since the
 * data is already loaded in the page.
 */
export function exportToCsv(filename: string, rows: Record<string, any>[]) {
  if (!rows || rows.length === 0) return;

  const headers = Array.from(
    rows.reduce<Set<string>>((set, row) => {
      Object.keys(row).forEach((k) => set.add(k));
      return set;
    }, new Set<string>())
  );

  const escapeCell = (value: any) => {
    if (value === null || value === undefined) return "";
    const str = typeof value === "object" ? JSON.stringify(value) : String(value);
    if (str.includes(",") || str.includes('"') || str.includes("\n")) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };

  const lines = [
    headers.join(","),
    ...rows.map((row) => headers.map((h) => escapeCell(row[h])).join(",")),
  ];

  const csvContent = lines.join("\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
CHAINSIGHT_APPLY_EOF

echo "Writing frontend/components/Pagination.tsx ..."
mkdir -p "$(dirname 'frontend/components/Pagination.tsx')"
cat > 'frontend/components/Pagination.tsx' << 'CHAINSIGHT_APPLY_EOF'
"use client";

import React from "react";
import { Download, ChevronLeft, ChevronRight } from "lucide-react";
import { exportToCsv } from "@/lib/csvExport";

export function ExportButton({ filename, rows }: { filename: string; rows: Record<string, any>[] }) {
  return (
    <button
      onClick={() => exportToCsv(filename, rows)}
      disabled={!rows || rows.length === 0}
      className="btn-secondary flex items-center gap-2 text-sm disabled:opacity-40 disabled:cursor-not-allowed"
      title={rows && rows.length ? `Export ${rows.length} rows to CSV` : "No rows to export"}
    >
      <Download size={14} /> Export CSV
    </button>
  );
}

export function Pagination({
  total, limit, offset, onOffsetChange,
}: {
  total: number; limit: number; offset: number; onOffsetChange: (offset: number) => void;
}) {
  if (total <= limit) return null;

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);

  return (
    <div className="flex items-center justify-between px-1 py-3 text-sm text-gray-400">
      <span>
        Showing {start}–{end} of {total}
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
          disabled={offset === 0}
          className="btn-secondary px-2 py-1 flex items-center disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="text-gray-500">Page {currentPage} of {totalPages}</span>
        <button
          onClick={() => onOffsetChange(offset + limit)}
          disabled={offset + limit >= total}
          className="btn-secondary px-2 py-1 flex items-center disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
CHAINSIGHT_APPLY_EOF

echo "Writing frontend/contexts/AuthContext.tsx ..."
mkdir -p "$(dirname 'frontend/contexts/AuthContext.tsx')"
cat > 'frontend/contexts/AuthContext.tsx' << 'CHAINSIGHT_APPLY_EOF'
"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, User } from "@/lib/api";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string, role: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const raw = typeof window !== "undefined" ? sessionStorage.getItem("chainsight_user") : null;
    if (raw) {
      try {
        setUser(JSON.parse(raw));
      } catch {
        // ignore
      }
    }
    setLoading(false);
  }, []);

  const persist = (token: string, u: User) => {
    sessionStorage.setItem("chainsight_token", token);
    sessionStorage.setItem("chainsight_user", JSON.stringify(u));
    setUser(u);
  };

  const login = async (email: string, password: string) => {
    const resp = await api.post("/api/v1/auth/login", { email, password });
    persist(resp.data.access_token, resp.data.user);
    router.push("/dashboard");
  };

  const register = async (email: string, password: string, fullName: string, role: string) => {
    const resp = await api.post("/api/v1/auth/register", {
      email, password, full_name: fullName, role,
    });
    persist(resp.data.access_token, resp.data.user);
    router.push("/dashboard");
  };

  const logout = () => {
    sessionStorage.removeItem("chainsight_token");
    sessionStorage.removeItem("chainsight_user");
    setUser(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
CHAINSIGHT_APPLY_EOF

echo "Writing frontend/app/page.tsx ..."
mkdir -p "$(dirname 'frontend/app/page.tsx')"
cat > 'frontend/app/page.tsx' << 'CHAINSIGHT_APPLY_EOF'
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    const token = typeof window !== "undefined" ? sessionStorage.getItem("chainsight_token") : null;
    router.replace(token ? "/dashboard" : "/login");
  }, [router]);
  return null;
}
CHAINSIGHT_APPLY_EOF

echo "Writing frontend/app/anomalies/page.tsx ..."
mkdir -p "$(dirname 'frontend/app/anomalies/page.tsx')"
cat > 'frontend/app/anomalies/page.tsx' << 'CHAINSIGHT_APPLY_EOF'
"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { PageHeader, LoadingState, ErrorState, Badge } from "@/components/Common";
import { ExportButton, Pagination } from "@/components/Pagination";
import { api, AnomalyRow, Paginated } from "@/lib/api";

const PAGE_SIZE = 25;

export default function AnomaliesPage() {
  const [anomalies, setAnomalies] = useState<AnomalyRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [severity, setSeverity] = useState("");
  const [entityType, setEntityType] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const params: any = { limit: PAGE_SIZE, offset };
      if (severity) params.severity = severity;
      if (entityType) params.entity_type = entityType;
      const resp = await api.get<Paginated<AnomalyRow>>("/api/v1/anomalies", { params });
      setAnomalies(resp.data.items);
      setTotal(resp.data.total);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load anomalies.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [severity, entityType, offset]);

  // filters reset pagination to page 1
  useEffect(() => {
    setOffset(0);
  }, [severity, entityType]);

  return (
    <AppShell>
      <PageHeader
        title="Anomaly Detection"
        subtitle="Isolation Forest + statistical bounds across demand, delivery delays, and quality signals"
        action={
          <div className="flex gap-2">
            <select className="input" value={entityType} onChange={(e) => setEntityType(e.target.value)}>
              <option value="">All Entities</option>
              <option value="product">Product (Demand)</option>
              <option value="supplier">Supplier</option>
            </select>
            <select className="input" value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="">All Severities</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <ExportButton filename="anomalies" rows={anomalies} />
          </div>
        }
      />

      {loading && <LoadingState label="Scanning for anomalies..." />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <>
          <div className="space-y-3">
            {anomalies.length === 0 && <p className="text-gray-500 text-sm">No anomalies match the current filters.</p>}
            {anomalies.map((a) => (
              <div key={a.id} className="card p-4 flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge level={a.severity} />
                    <span className="text-xs text-gray-500 uppercase tracking-wide">{a.entity_type} · {a.metric_name.replace("_", " ")}</span>
                    <span className="text-xs text-gray-600">{a.detected_date}</span>
                  </div>
                  <p className="text-white text-sm font-medium">{a.entity_name || `#${a.entity_id}`}</p>
                  <p className="text-sm text-gray-400 mt-1">{a.description}</p>
                  <p className="text-xs text-gray-600 mt-1">
                    Observed: <span className="text-gray-400">{a.metric_value}</span> · Expected range:{" "}
                    <span className="text-gray-400">{a.expected_range_low.toFixed(1)} – {a.expected_range_high.toFixed(1)}</span>
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-gray-500">Anomaly Score</p>
                  <p className="text-white font-semibold">{a.anomaly_score.toFixed(2)}</p>
                </div>
              </div>
            ))}
          </div>
          <Pagination total={total} limit={PAGE_SIZE} offset={offset} onOffsetChange={setOffset} />
        </>
      )}
    </AppShell>
  );
}
CHAINSIGHT_APPLY_EOF

echo "Writing frontend/app/risk/page.tsx ..."
mkdir -p "$(dirname 'frontend/app/risk/page.tsx')"
cat > 'frontend/app/risk/page.tsx' << 'CHAINSIGHT_APPLY_EOF'
"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { PageHeader, LoadingState, ErrorState, Badge } from "@/components/Common";
import { ExportButton, Pagination } from "@/components/Pagination";
import { api, StockoutRisk, Paginated } from "@/lib/api";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";

const PAGE_SIZE = 25;

export default function RiskPage() {
  const [risks, setRisks] = useState<StockoutRisk[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<StockoutRisk | null>(null);
  const [riskLevel, setRiskLevel] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const params: any = { limit: PAGE_SIZE, offset };
      if (riskLevel) params.risk_level = riskLevel;
      const resp = await api.get<Paginated<StockoutRisk>>("/api/v1/risk/stockout", { params });
      setRisks(resp.data.items);
      setTotal(resp.data.total);
      setSelected(resp.data.items[0] || null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load risk scores.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [riskLevel, offset]);

  useEffect(() => {
    setOffset(0);
  }, [riskLevel]);

  const exportRows = risks.map((r) => ({
    sku: r.sku, product_name: r.product_name, warehouse_id: r.warehouse_id,
    risk_probability: r.risk_probability, risk_level: r.risk_level,
    days_of_supply: r.days_of_supply, on_hand_units: r.on_hand_units,
    avg_daily_demand: r.avg_daily_demand, supplier_name: r.supplier_name,
    top_factor: r.explanation?.[0]?.detail || "",
  }));

  return (
    <AppShell>
      <PageHeader
        title="Stockout Risk Prediction"
        subtitle="RandomForest classifier estimating P(stockout within 14 days), paired with per-factor explanations"
        action={
          <div className="flex gap-2">
            <select className="input" value={riskLevel} onChange={(e) => setRiskLevel(e.target.value)}>
              <option value="">All Levels</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <ExportButton filename="stockout-risk" rows={exportRows} />
          </div>
        }
      />

      {loading && <LoadingState label="Scoring stockout risk..." />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <div className="card overflow-hidden max-h-[560px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-panel">
                  <tr className="text-left text-gray-500 border-b border-[#1e2a44] text-xs uppercase">
                    <th className="p-3">SKU</th>
                    <th className="p-3">Days of Supply</th>
                    <th className="p-3">Risk Probability</th>
                    <th className="p-3">Level</th>
                  </tr>
                </thead>
                <tbody>
                  {risks.map((r) => (
                    <tr
                      key={`${r.product_id}-${r.warehouse_id}`}
                      onClick={() => setSelected(r)}
                      className={`border-b border-[#1e2a44] cursor-pointer hover:bg-[#182238] ${selected?.product_id === r.product_id ? "bg-[#182238]" : ""}`}
                    >
                      <td className="p-3 text-white font-medium">{r.sku}<div className="text-xs text-gray-500">{r.product_name}</div></td>
                      <td className="p-3 text-gray-300">{r.days_of_supply.toFixed(1)}</td>
                      <td className="p-3">
                        <div className="w-32 bg-[#1e2a44] rounded-full h-2">
                          <div
                            className="h-2 rounded-full bg-red-500"
                            style={{ width: `${Math.min(100, r.risk_probability * 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400">{(r.risk_probability * 100).toFixed(0)}%</span>
                      </td>
                      <td className="p-3"><Badge level={r.risk_level} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination total={total} limit={PAGE_SIZE} offset={offset} onOffsetChange={setOffset} />
          </div>

          <div className="card p-5">
            {selected ? (
              <>
                <h3 className="text-white font-semibold">{selected.sku}</h3>
                <p className="text-xs text-gray-500 mb-1">{selected.product_name}</p>
                <p className="text-xs text-gray-500 mb-4">Supplier: {selected.supplier_name || "—"}</p>

                <div className="flex items-center gap-3 mb-4">
                  <div className="text-3xl font-bold text-white">{(selected.risk_probability * 100).toFixed(0)}%</div>
                  <Badge level={selected.risk_level} />
                </div>

                <div className="grid grid-cols-2 gap-3 text-sm mb-4">
                  <div>
                    <p className="text-gray-500 text-xs">On Hand</p>
                    <p className="text-white font-medium">{selected.on_hand_units.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-gray-500 text-xs">Avg Daily Demand</p>
                    <p className="text-white font-medium">{selected.avg_daily_demand.toFixed(1)}</p>
                  </div>
                </div>

                <h4 className="text-xs uppercase text-gray-500 font-semibold mb-2">Why this risk exists</h4>
                <div className="space-y-2">
                  {selected.explanation.map((f, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm">
                      {f.direction === "increases_risk" ? (
                        <ArrowUpRight className="text-red-400 mt-0.5 shrink-0" size={16} />
                      ) : (
                        <ArrowDownRight className="text-emerald-400 mt-0.5 shrink-0" size={16} />
                      )}
                      <div>
                        <p className="text-gray-300 font-medium">{f.factor}</p>
                        <p className="text-gray-500 text-xs">{f.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-gray-500 text-sm">Select a SKU to see the risk explanation.</p>
            )}
          </div>
        </div>
      )}
    </AppShell>
  );
}
CHAINSIGHT_APPLY_EOF

echo "Writing frontend/app/inventory/page.tsx ..."
mkdir -p "$(dirname 'frontend/app/inventory/page.tsx')"
cat > 'frontend/app/inventory/page.tsx' << 'CHAINSIGHT_APPLY_EOF'
"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { PageHeader, LoadingState, ErrorState, Badge } from "@/components/Common";
import { ExportButton, Pagination } from "@/components/Pagination";
import { api, InventoryHealthRow, Paginated } from "@/lib/api";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";

const STATUS_COLORS: Record<string, string> = {
  healthy: "#4ade80",
  low: "#facc15",
  critical: "#f87171",
  overstock: "#38bdf8",
};

const PAGE_SIZE = 50;

export default function InventoryPage() {
  const [rows, setRows] = useState<InventoryHealthRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [abc, setAbc] = useState<any[]>([]);
  const [statusCounts, setStatusCounts] = useState<any[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const params: any = { limit: PAGE_SIZE, offset };
      if (statusFilter) params.status = statusFilter;
      if (categoryFilter) params.category = categoryFilter;
      const [inv, abcResp, cats] = await Promise.all([
        api.get<Paginated<InventoryHealthRow>>("/api/v1/inventory/health", { params }),
        api.get("/api/v1/inventory/abc-analysis"),
        api.get("/api/v1/catalog/categories"),
      ]);
      setRows(inv.data.items);
      setTotal(inv.data.total);
      setAbc(abcResp.data);
      setCategories(cats.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load inventory data.");
    } finally {
      setLoading(false);
    }
  };

  // separate lightweight call to get status breakdown across ALL pages (not just current page)
  const loadStatusBreakdown = async () => {
    try {
      const results = await Promise.all(
        ["healthy", "low", "critical", "overstock"].map((s) =>
          api.get<Paginated<InventoryHealthRow>>("/api/v1/inventory/health", { params: { status: s, limit: 1 } })
        )
      );
      setStatusCounts(
        ["healthy", "low", "critical", "overstock"].map((s, i) => ({ name: s, value: results[i].data.total }))
      );
    } catch {
      // non-critical widget; ignore failures
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, categoryFilter, offset]);

  useEffect(() => {
    loadStatusBreakdown();
  }, []);

  useEffect(() => {
    setOffset(0);
  }, [statusFilter, categoryFilter]);

  return (
    <AppShell>
      <PageHeader
        title="Inventory Health & ABC Analysis"
        subtitle="Days-of-supply computed live from on-hand units vs. trailing 30-day demand"
        action={
          <div className="flex gap-2">
            <select className="input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All Statuses</option>
              <option value="critical">Critical</option>
              <option value="low">Low</option>
              <option value="healthy">Healthy</option>
              <option value="overstock">Overstock</option>
            </select>
            <select className="input" value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
              <option value="">All Categories</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <ExportButton filename="inventory-health" rows={rows} />
          </div>
        }
      />

      {loading && <LoadingState label="Analyzing inventory positions..." />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <div className="card overflow-hidden max-h-[560px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-panel">
                  <tr className="text-left text-gray-500 border-b border-[#1e2a44] text-xs uppercase">
                    <th className="p-3">SKU</th>
                    <th className="p-3">Product</th>
                    <th className="p-3">ABC</th>
                    <th className="p-3">On Hand</th>
                    <th className="p-3">Days of Supply</th>
                    <th className="p-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={`${r.product_id}-${r.warehouse_id}`} className="border-b border-[#1e2a44] hover:bg-[#182238]">
                      <td className="p-3 text-gray-300 font-mono text-xs">{r.sku}</td>
                      <td className="p-3 text-white">{r.name}<div className="text-xs text-gray-500">{r.warehouse_name}</div></td>
                      <td className="p-3 text-gray-400">{r.abc_class}</td>
                      <td className="p-3 text-gray-300">{r.on_hand_units.toLocaleString()}</td>
                      <td className="p-3 text-gray-300">{r.days_of_supply?.toFixed(1)}</td>
                      <td className="p-3"><Badge level={r.inventory_status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination total={total} limit={PAGE_SIZE} offset={offset} onOffsetChange={setOffset} />
          </div>

          <div className="space-y-4">
            <div className="card p-5">
              <h3 className="text-sm font-semibold text-gray-300 mb-4">Status Breakdown</h3>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={statusCounts} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} paddingAngle={3}>
                    {statusCounts.map((entry) => (
                      <Cell key={entry.name} fill={STATUS_COLORS[entry.name]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: "#111a2e", border: "1px solid #263352" }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="card p-5">
              <h3 className="text-sm font-semibold text-gray-300 mb-4">ABC Revenue Contribution</h3>
              <div className="space-y-3">
                {abc.map((a) => (
                  <div key={a.abc_class || "unclassified"}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-gray-300">Class {a.abc_class || "—"}</span>
                      <span className="text-gray-500">{a.sku_count} SKUs</span>
                    </div>
                    <div className="text-white font-semibold">${Number(a.revenue || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
CHAINSIGHT_APPLY_EOF

echo "Writing frontend/app/recommendations/page.tsx ..."
mkdir -p "$(dirname 'frontend/app/recommendations/page.tsx')"
cat > 'frontend/app/recommendations/page.tsx' << 'CHAINSIGHT_APPLY_EOF'
"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { PageHeader, LoadingState, ErrorState, Badge } from "@/components/Common";
import { ExportButton, Pagination } from "@/components/Pagination";
import { api, Recommendation, Paginated } from "@/lib/api";
import { CheckCircle2 } from "lucide-react";

const categoryLabel: Record<string, string> = {
  supplier: "Supplier",
  inventory: "Inventory",
  procurement: "Procurement",
  quality: "Quality",
};

const PAGE_SIZE = 25;

export default function RecommendationsPage() {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const params: any = { resolved: false, limit: PAGE_SIZE, offset };
      if (category) params.category = category;
      if (priority) params.priority = priority;
      const resp = await api.get<Paginated<Recommendation>>("/api/v1/recommendations", { params });
      setRecs(resp.data.items);
      setTotal(resp.data.total);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load recommendations.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, priority, offset]);

  useEffect(() => {
    setOffset(0);
  }, [category, priority]);

  const resolve = async (id: number) => {
    await api.patch(`/api/v1/recommendations/${id}/resolve`);
    setRecs((prev) => prev.filter((r) => r.id !== id));
    setTotal((t) => Math.max(0, t - 1));
  };

  return (
    <AppShell>
      <PageHeader
        title="Actionable Recommendations"
        subtitle="Synthesized from supplier scores, inventory health, stockout risk, and detected anomalies"
        action={
          <div className="flex gap-2">
            <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All Categories</option>
              <option value="supplier">Supplier</option>
              <option value="inventory">Inventory</option>
              <option value="procurement">Procurement</option>
              <option value="quality">Quality</option>
            </select>
            <select className="input" value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="">All Priorities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <ExportButton filename="recommendations" rows={recs} />
          </div>
        }
      />

      {loading && <LoadingState label="Synthesizing recommendations..." />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <>
          <div className="space-y-3">
            {recs.length === 0 && <p className="text-gray-500 text-sm">No open recommendations match the current filters. 🎉</p>}
            {recs.map((r) => (
              <div key={r.id} className="card p-4 flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge level={r.priority} />
                    <span className="text-xs text-gray-500 uppercase tracking-wide">{categoryLabel[r.category] || r.category}</span>
                  </div>
                  <p className="text-white font-medium">{r.title}</p>
                  <p className="text-sm text-gray-400 mt-1">{r.description}</p>
                  {r.estimated_impact && (
                    <p className="text-xs text-emerald-400/80 mt-2">Impact: {r.estimated_impact}</p>
                  )}
                </div>
                <button onClick={() => resolve(r.id)} className="btn-secondary flex items-center gap-2 text-sm shrink-0">
                  <CheckCircle2 size={16} /> Mark Resolved
                </button>
              </div>
            ))}
          </div>
          <Pagination total={total} limit={PAGE_SIZE} offset={offset} onOffsetChange={setOffset} />
        </>
      )}
    </AppShell>
  );
}
CHAINSIGHT_APPLY_EOF

echo "Writing frontend/app/suppliers/page.tsx ..."
mkdir -p "$(dirname 'frontend/app/suppliers/page.tsx')"
cat > 'frontend/app/suppliers/page.tsx' << 'CHAINSIGHT_APPLY_EOF'
"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { PageHeader, LoadingState, ErrorState } from "@/components/Common";
import { ExportButton } from "@/components/Pagination";
import { api, SupplierScore } from "@/lib/api";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip,
} from "recharts";

const gradeColor: Record<string, string> = {
  A: "text-emerald-400 bg-emerald-400/10",
  B: "text-sky-400 bg-sky-400/10",
  C: "text-amber-400 bg-amber-400/10",
  D: "text-red-400 bg-red-400/10",
};

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<SupplierScore[]>([]);
  const [selected, setSelected] = useState<SupplierScore | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [regionFilter, setRegionFilter] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const resp = await api.get("/api/v1/suppliers/scores");
        setSuppliers(resp.data);
        setSelected(resp.data[0] || null);
      } catch (e: any) {
        setError(e?.response?.data?.detail || "Failed to load supplier scores.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const regions = Array.from(new Set(suppliers.map((s) => s.region)));
  const filtered = regionFilter ? suppliers.filter((s) => s.region === regionFilter) : suppliers;

  const radarData = selected
    ? Object.entries(selected.component_scores).map(([k, v]) => ({
        metric: k.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        score: v,
      }))
    : [];

  return (
    <AppShell>
      <PageHeader
        title="Supplier Performance Scoring"
        subtitle="Composite scorecard: 35% on-time delivery, 30% quality, 20% cost, 15% lead-time consistency"
        action={
          <div className="flex gap-2">
            <select className="input" value={regionFilter} onChange={(e) => setRegionFilter(e.target.value)}>
              <option value="">All Regions</option>
              {regions.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <ExportButton filename="supplier-scores" rows={filtered} />
          </div>
        }
      />

      {loading && <LoadingState label="Scoring suppliers..." />}
      {error && <ErrorState message={error} />}

      {!loading && !error && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 card overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-[#1e2a44] text-xs uppercase">
                  <th className="p-3">Supplier</th>
                  <th className="p-3">Region</th>
                  <th className="p-3">On-Time</th>
                  <th className="p-3">Defect Rate</th>
                  <th className="p-3">Cost Idx</th>
                  <th className="p-3">Score</th>
                  <th className="p-3">Grade</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr
                    key={s.supplier_id}
                    onClick={() => setSelected(s)}
                    className={`border-b border-[#1e2a44] cursor-pointer hover:bg-[#182238] ${selected?.supplier_id === s.supplier_id ? "bg-[#182238]" : ""}`}
                  >
                    <td className="p-3 text-white font-medium">{s.name}</td>
                    <td className="p-3 text-gray-400">{s.region}</td>
                    <td className="p-3 text-gray-300">{(s.on_time_rate * 100).toFixed(0)}%</td>
                    <td className="p-3 text-gray-300">{(s.defect_rate * 100).toFixed(1)}%</td>
                    <td className="p-3 text-gray-300">{s.cost_index.toFixed(2)}</td>
                    <td className="p-3 text-white font-semibold">{s.composite_score.toFixed(0)}</td>
                    <td className="p-3">
                      <span className={`badge ${gradeColor[s.grade]}`}>{s.grade}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card p-5">
            {selected ? (
              <>
                <h3 className="text-white font-semibold mb-1">{selected.name}</h3>
                <p className="text-xs text-gray-500 mb-4">{selected.category} · {selected.region}</p>
                <ResponsiveContainer width="100%" height={240}>
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="#263352" />
                    <PolarAngleAxis dataKey="metric" tick={{ fill: "#9aa7c2", fontSize: 11 }} />
                    <PolarRadiusAxis domain={[0, 100]} tick={{ fill: "#4a5573", fontSize: 9 }} />
                    <Radar dataKey="score" stroke="#2456f5" fill="#2456f5" fillOpacity={0.4} />
                    <Tooltip contentStyle={{ background: "#111a2e", border: "1px solid #263352" }} />
                  </RadarChart>
                </ResponsiveContainer>
                <div className="grid grid-cols-2 gap-3 mt-4 text-sm">
                  <div>
                    <p className="text-gray-500 text-xs">Avg Delay</p>
                    <p className="text-white font-medium">{selected.avg_delay_days.toFixed(1)} days</p>
                  </div>
                  <div>
                    <p className="text-gray-500 text-xs">Lead Time Variability</p>
                    <p className="text-white font-medium">±{selected.lead_time_variability.toFixed(1)} days</p>
                  </div>
                </div>
              </>
            ) : (
              <p className="text-gray-500 text-sm">Select a supplier to view detail.</p>
            )}
          </div>
        </div>
      )}
    </AppShell>
  );
}
CHAINSIGHT_APPLY_EOF

echo "Writing frontend/package.json ..."
mkdir -p "$(dirname 'frontend/package.json')"
cat > 'frontend/package.json' << 'CHAINSIGHT_APPLY_EOF'
{
  "name": "chainsight-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev -p 3000",
    "build": "next build",
    "start": "next start -p 3000",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "14.2.35",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "recharts": "2.12.7",
    "axios": "1.20.0",
    "lucide-react": "0.400.0",
    "clsx": "2.1.1",
    "date-fns": "3.6.0"
  },
  "devDependencies": {
    "typescript": "5.5.4",
    "@types/node": "20.14.15",
    "@types/react": "18.3.3",
    "@types/react-dom": "18.3.0",
    "tailwindcss": "3.4.7",
    "postcss": "8.5.28",
    "autoprefixer": "10.4.19",
    "eslint": "8.57.0",
    "eslint-config-next": "14.2.35"
  },
  "overrides": {
    "postcss": "8.5.28"
  }
}
CHAINSIGHT_APPLY_EOF

echo "Writing .github/workflows/ci.yml ..."
mkdir -p "$(dirname '.github/workflows/ci.yml')"
cat > '.github/workflows/ci.yml' << 'CHAINSIGHT_APPLY_EOF'
name: CI

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]
  workflow_dispatch: {}

jobs:
  backend-tests:
    name: Backend (pytest)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
          cache-dependency-path: backend/requirements.txt

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run test suite
        run: pytest -v

  frontend-build:
    name: Frontend (build + typecheck)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: npm install --legacy-peer-deps

      - name: Build (includes TypeScript type-checking)
        env:
          NEXT_PUBLIC_API_URL: http://localhost:8000
        run: npm run build

  docker-build:
    name: Docker images build
    runs-on: ubuntu-latest
    needs: [backend-tests, frontend-build]
    steps:
      - uses: actions/checkout@v4

      - name: Build backend image
        run: docker build -f backend/Dockerfile -t chainsight-backend:ci .

      - name: Build frontend image
        run: docker build -f frontend/Dockerfile -t chainsight-frontend:ci .
CHAINSIGHT_APPLY_EOF


echo ""
echo "All files updated successfully."
echo ""
echo "NEXT STEPS:"
echo "  1. Rebuild the frontend lockfile (dependency versions changed):"
echo "         cd frontend && rm -rf node_modules package-lock.json && cd .."
echo ""
echo "  2. Rebuild and restart everything fresh:"
echo "         docker compose down -v"
echo "         docker compose up --build"
echo ""
echo "     (-v clears the old database volume; not required for this update"
echo "      specifically, but recommended since the schema/pipeline haven't"
echo "      changed and a clean rebuild avoids any stale image layers)"
echo ""
echo "  3. New demo accounts still work as before:"
echo "         admin@chainsight.io    / Admin123!"
echo "         analyst@chainsight.io  / Analyst123!"
echo "         viewer@chainsight.io   / Viewer123!"
echo ""
echo "  4. You can now register with real personal emails without DNS-related"
echo "     failures, and log into different accounts in different browser tabs"
echo "     simultaneously."
