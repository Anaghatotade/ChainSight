"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { PageHeader, LoadingState, ErrorState } from "@/components/Common";
import { api, Product, Warehouse, ForecastResponse } from "@/lib/api";
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

export default function ForecastingPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [productId, setProductId] = useState<number | null>(null);
  const [warehouseId, setWarehouseId] = useState<number | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [accuracy, setAccuracy] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [p, w, acc] = await Promise.all([
          api.get("/api/v1/catalog/products"),
          api.get("/api/v1/catalog/warehouses"),
          api.get("/api/v1/forecasting/accuracy/summary"),
        ]);
        setProducts(p.data);
        setWarehouses(w.data);
        setAccuracy(acc.data);
        if (p.data.length && w.data.length) {
          setProductId(p.data[0].id);
          setWarehouseId(w.data[0].id);
        }
      } catch (e: any) {
        setError(e?.response?.data?.detail || "Failed to load catalog.");
      }
    })();
  }, []);

  useEffect(() => {
    if (!productId || !warehouseId) return;
    setLoading(true);
    api
      .get(`/api/v1/forecasting/${productId}/${warehouseId}`)
      .then((resp) => setForecast(resp.data))
      .catch((e) => setError(e?.response?.data?.detail || "No forecast available for this combination."))
      .finally(() => setLoading(false));
  }, [productId, warehouseId]);

  const chartData = forecast
    ? [
        ...forecast.history.map((h) => ({ date: h.date, actual: h.actual_units, forecast: null, lower: null, upper: null })),
        ...forecast.forecast.map((f) => ({ date: f.date, actual: null, forecast: f.forecast_units, lower: f.lower_bound, upper: f.upper_bound })),
      ]
    : [];

  return (
    <AppShell>
      <PageHeader
        title="Demand Forecasting"
        subtitle="Random Forest regression over lag & calendar features, with 30-day forward forecast and confidence band"
        action={
          <div className="flex gap-2">
            <select className="input" value={productId ?? ""} onChange={(e) => setProductId(Number(e.target.value))}>
              {products.map((p) => <option key={p.id} value={p.id}>{p.sku} — {p.name}</option>)}
            </select>
            <select className="input" value={warehouseId ?? ""} onChange={(e) => setWarehouseId(Number(e.target.value))}>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>
        }
      />

      {accuracy && accuracy.avg_mape != null && (
        <div className="card p-4 mb-4 flex gap-8 text-sm">
          <div>
            <p className="text-gray-500 text-xs">Sampled Backtest MAE</p>
            <p className="text-white font-semibold">{accuracy.avg_mae} units</p>
          </div>
          <div>
            <p className="text-gray-500 text-xs">Sampled Backtest MAPE</p>
            <p className="text-white font-semibold">{accuracy.avg_mape}%</p>
          </div>
          <div>
            <p className="text-gray-500 text-xs">Sample Size</p>
            <p className="text-white font-semibold">{accuracy.sample_size} SKU series</p>
          </div>
        </div>
      )}

      {loading && <LoadingState label="Training / loading forecast model..." />}
      {error && <ErrorState message={error} />}

      {!loading && forecast && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-300">
              {forecast.sku} — Historical Demand & 30-Day Forecast ({forecast.model_name.replace("_", " ")})
            </h3>
            {forecast.mae != null && (
              <span className="text-xs text-gray-500">Backtest MAE: {forecast.mae} · MAPE: {forecast.mape}%</span>
            )}
          </div>
          <ResponsiveContainer width="100%" height={380}>
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2a44" />
              <XAxis dataKey="date" tick={{ fill: "#6b7a99", fontSize: 10 }} minTickGap={40} />
              <YAxis tick={{ fill: "#6b7a99", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#111a2e", border: "1px solid #263352" }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area type="monotone" dataKey="upper" stroke="none" fill="#2456f5" fillOpacity={0.08} name="Confidence Band" />
              <Area type="monotone" dataKey="lower" stroke="none" fill="#0b1220" fillOpacity={1} name="" legendType="none" />
              <Line type="monotone" dataKey="actual" stroke="#4ade80" dot={false} strokeWidth={2} name="Actual Demand" />
              <Line type="monotone" dataKey="forecast" stroke="#facc15" strokeWidth={2} strokeDasharray="5 3" dot={false} name="Forecast" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </AppShell>
  );
}
