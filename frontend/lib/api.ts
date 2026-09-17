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
