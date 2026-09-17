"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { PageHeader, LoadingState, ErrorState } from "@/components/Common";
import { api, Product, Warehouse, SimulationResult } from "@/lib/api";
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { Play, Loader2 } from "lucide-react";

function Slider({ label, value, onChange, min, max, step, unit }: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step: number; unit: string;
}) {
  return (
    <div className="mb-4">
      <div className="flex justify-between text-sm mb-1">
        <span className="text-gray-300">{label}</span>
        <span className="text-white font-medium">{value > 0 ? "+" : ""}{value}{unit}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-brand-500"
      />
    </div>
  );
}

export default function SimulatorPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [productId, setProductId] = useState<number | null>(null);
  const [warehouseId, setWarehouseId] = useState<number | null>(null);

  const [demandChange, setDemandChange] = useState(0);
  const [leadTimeChange, setLeadTimeChange] = useState(0);
  const [capacityChange, setCapacityChange] = useState(0);
  const [safetyStockChange, setSafetyStockChange] = useState(0);
  const [costChange, setCostChange] = useState(0);
  const [simDays, setSimDays] = useState(90);

  const [result, setResult] = useState<SimulationResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const [p, w] = await Promise.all([
        api.get("/api/v1/catalog/products"),
        api.get("/api/v1/catalog/warehouses"),
      ]);
      setProducts(p.data);
      setWarehouses(w.data);
      if (p.data.length && w.data.length) {
        setProductId(p.data[0].id);
        setWarehouseId(w.data[0].id);
      }
    })();
  }, []);

  const runSimulation = async () => {
    if (!productId || !warehouseId) return;
    setRunning(true);
    setError(null);
    try {
      const resp = await api.post("/api/v1/simulator/run", {
        product_id: productId,
        warehouse_id: warehouseId,
        demand_change_pct: demandChange,
        lead_time_change_days: leadTimeChange,
        supplier_capacity_change_pct: capacityChange,
        safety_stock_change_units: safetyStockChange,
        cost_change_pct: costChange,
        simulation_days: simDays,
      });
      setResult(resp.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Simulation failed. Try different parameters.");
    } finally {
      setRunning(false);
    }
  };

  const chartData = result
    ? result.timeline_baseline.map((b, i) => ({
        day: b.day,
        baseline_on_hand: b.projected_on_hand,
        scenario_on_hand: result.timeline_scenario[i]?.projected_on_hand,
      }))
    : [];

  return (
    <AppShell>
      <PageHeader
        title="What-If Simulator"
        subtitle="Compare baseline vs. scenario inventory outcomes under changed demand, lead time, capacity, safety stock, and cost"
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card p-5">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">Scenario Parameters</h3>

          <div className="mb-4">
            <label className="block text-xs text-gray-500 mb-1">Product</label>
            <select className="input w-full" value={productId ?? ""} onChange={(e) => setProductId(Number(e.target.value))}>
              {products.map((p) => <option key={p.id} value={p.id}>{p.sku} — {p.name}</option>)}
            </select>
          </div>
          <div className="mb-6">
            <label className="block text-xs text-gray-500 mb-1">Warehouse</label>
            <select className="input w-full" value={warehouseId ?? ""} onChange={(e) => setWarehouseId(Number(e.target.value))}>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>

          <Slider label="Demand Change" value={demandChange} onChange={setDemandChange} min={-50} max={100} step={5} unit="%" />
          <Slider label="Lead Time Change" value={leadTimeChange} onChange={setLeadTimeChange} min={-10} max={30} step={1} unit=" days" />
          <Slider label="Supplier Capacity Change" value={capacityChange} onChange={setCapacityChange} min={-50} max={50} step={5} unit="%" />
          <Slider label="Safety Stock Change" value={safetyStockChange} onChange={setSafetyStockChange} min={-50} max={300} step={10} unit=" units" />
          <Slider label="Unit Cost Change" value={costChange} onChange={setCostChange} min={-30} max={50} step={5} unit="%" />
          <Slider label="Simulation Horizon" value={simDays} onChange={setSimDays} min={30} max={180} step={30} unit=" days" />

          <button onClick={runSimulation} disabled={running} className="btn-primary w-full flex items-center justify-center gap-2 mt-2">
            {running ? <Loader2 className="animate-spin" size={16} /> : <Play size={16} />}
            Run Simulation
          </button>
          {error && <p className="text-red-400 text-sm mt-3">{error}</p>}
        </div>

        <div className="lg:col-span-2 space-y-4">
          {running && <LoadingState label="Simulating scenario..." />}

          {result && !running && (
            <>
              <div className="grid grid-cols-3 gap-3">
                <div className="card p-4">
                  <p className="text-xs text-gray-500">Service Level Δ</p>
                  <p className={`text-xl font-bold ${result.delta.service_level_pp < 0 ? "text-red-400" : "text-emerald-400"}`}>
                    {result.delta.service_level_pp > 0 ? "+" : ""}{result.delta.service_level_pp}pp
                  </p>
                  <p className="text-xs text-gray-600">baseline {(result.baseline.service_level * 100).toFixed(1)}% → scenario {(result.scenario.service_level * 100).toFixed(1)}%</p>
                </div>
                <div className="card p-4">
                  <p className="text-xs text-gray-500">Stockout Days Δ</p>
                  <p className={`text-xl font-bold ${result.delta.stockout_days_diff > 0 ? "text-red-400" : "text-emerald-400"}`}>
                    {result.delta.stockout_days_diff > 0 ? "+" : ""}{result.delta.stockout_days_diff}
                  </p>
                  <p className="text-xs text-gray-600">baseline {result.baseline.stockout_days} → scenario {result.scenario.stockout_days}</p>
                </div>
                <div className="card p-4">
                  <p className="text-xs text-gray-500">Procurement Cost Δ</p>
                  <p className={`text-xl font-bold ${result.delta.procurement_cost_diff > 0 ? "text-amber-400" : "text-emerald-400"}`}>
                    {result.delta.procurement_cost_diff > 0 ? "+" : ""}${Number(result.delta.procurement_cost_diff).toLocaleString()}
                  </p>
                  <p className="text-xs text-gray-600">{result.delta.procurement_cost_pct > 0 ? "+" : ""}{result.delta.procurement_cost_pct}%</p>
                </div>
              </div>

              <div className="card p-5">
                <h3 className="text-sm font-semibold text-gray-300 mb-4">Projected On-Hand Inventory: Baseline vs. Scenario</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <ComposedChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e2a44" />
                    <XAxis dataKey="day" tick={{ fill: "#6b7a99", fontSize: 11 }} label={{ value: "Day", position: "insideBottom", offset: -5, fill: "#6b7a99" }} />
                    <YAxis tick={{ fill: "#6b7a99", fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: "#111a2e", border: "1px solid #263352" }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="baseline_on_hand" stroke="#4ade80" strokeWidth={2} dot={false} name="Baseline" />
                    <Line type="monotone" dataKey="scenario_on_hand" stroke="#f87171" strokeWidth={2} dot={false} name="Scenario" />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>

              <div className="card p-5">
                <h3 className="text-sm font-semibold text-gray-300 mb-3">Insight Narrative</h3>
                <ul className="space-y-2">
                  {result.narrative.map((n, i) => (
                    <li key={i} className="text-sm text-gray-400 flex gap-2">
                      <span className="text-brand-400">•</span>{n}
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}

          {!result && !running && (
            <div className="card p-10 text-center text-gray-500 text-sm">
              Adjust parameters and click "Run Simulation" to compare baseline vs. scenario outcomes.
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
