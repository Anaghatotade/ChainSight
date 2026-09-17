"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import KPICard from "@/components/KPICard";
import { LoadingState, ErrorState, PageHeader } from "@/components/Common";
import { api, KPISummary } from "@/lib/api";
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import {
  DollarSign, Package, TrendingUp, Truck, ShieldAlert, AlertTriangle, Repeat, Award,
} from "lucide-react";

export default function DashboardPage() {
  const [kpis, setKpis] = useState<KPISummary | null>(null);
  const [invTrend, setInvTrend] = useState<any[]>([]);
  const [fillTrend, setFillTrend] = useState<any[]>([]);
  const [otifByCategory, setOtifByCategory] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [k, it, ft, oc] = await Promise.all([
          api.get("/api/v1/kpis/summary"),
          api.get("/api/v1/kpis/trends/inventory-value", { params: { days: 90 } }),
          api.get("/api/v1/kpis/trends/fill-rate", { params: { days: 90 } }),
          api.get("/api/v1/kpis/trends/otif-by-category"),
        ]);
        setKpis(k.data);
        setInvTrend(it.data.map((d: any) => ({ ...d, value: Math.round(d.value) })));
        setFillTrend(ft.data.map((d: any) => ({ ...d, fill_rate: Math.round(d.fill_rate * 1000) / 10 })));
        setOtifByCategory(oc.data.map((d: any) => ({ ...d, otif_rate: Math.round(d.otif_rate * 1000) / 10 })));
      } catch (e: any) {
        setError(e?.response?.data?.detail || "Failed to load dashboard data.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <AppShell>
      <PageHeader title="Executive Dashboard" subtitle="Real-time supply chain performance, computed live from operational data" />

      {loading && <LoadingState label="Crunching supply chain metrics..." />}
      {error && <ErrorState message={error} />}

      {kpis && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <KPICard label="Inventory Value" value={`$${(kpis.total_on_hand_value / 1000).toFixed(0)}K`} icon={DollarSign} sublabel={`${kpis.total_skus} active SKUs`} />
            <KPICard label="Fill Rate" value={`${(kpis.fill_rate * 100).toFixed(1)}%`} icon={Package} accent="text-emerald-400" />
            <KPICard label="OTIF Rate" value={`${(kpis.otif_rate * 100).toFixed(1)}%`} icon={Truck} accent="text-sky-400" sublabel="On-time in-full" />
            <KPICard label="Inventory Turnover" value={`${kpis.avg_inventory_turnover.toFixed(1)}x`} icon={Repeat} accent="text-purple-400" sublabel="Annualized" />
            <KPICard label="Avg Lead Time" value={`${kpis.avg_lead_time_days.toFixed(1)} days`} icon={TrendingUp} accent="text-amber-400" />
            <KPICard label="Open POs" value={`${kpis.open_pos}`} icon={Package} accent="text-gray-300" />
            <KPICard label="At-Risk SKUs" value={`${kpis.at_risk_skus}`} icon={ShieldAlert} accent="text-red-400" sublabel="High/critical stockout risk" />
            <KPICard label="Anomalies (30d)" value={`${kpis.total_anomalies_30d}`} icon={AlertTriangle} accent="text-orange-400" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            <div className="card p-5">
              <h3 className="text-sm font-semibold text-gray-300 mb-4">Inventory Value Trend (90 days)</h3>
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={invTrend}>
                  <defs>
                    <linearGradient id="invGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#2456f5" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#2456f5" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e2a44" />
                  <XAxis dataKey="date" tick={{ fill: "#6b7a99", fontSize: 11 }} minTickGap={30} />
                  <YAxis tick={{ fill: "#6b7a99", fontSize: 11 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`} />
                  <Tooltip contentStyle={{ background: "#111a2e", border: "1px solid #263352" }} formatter={(v: any) => `$${Number(v).toLocaleString()}`} />
                  <Area type="monotone" dataKey="value" stroke="#2456f5" fill="url(#invGrad)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="card p-5">
              <h3 className="text-sm font-semibold text-gray-300 mb-4">Fill Rate Trend (90 days)</h3>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={fillTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e2a44" />
                  <XAxis dataKey="date" tick={{ fill: "#6b7a99", fontSize: 11 }} minTickGap={30} />
                  <YAxis tick={{ fill: "#6b7a99", fontSize: 11 }} domain={[70, 100]} tickFormatter={(v) => `${v}%`} />
                  <Tooltip contentStyle={{ background: "#111a2e", border: "1px solid #263352" }} formatter={(v: any) => `${v}%`} />
                  <Line type="monotone" dataKey="fill_rate" stroke="#4ade80" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card p-5">
            <h3 className="text-sm font-semibold text-gray-300 mb-4">OTIF Rate by Product Category</h3>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={otifByCategory} layout="vertical" margin={{ left: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2a44" />
                <XAxis type="number" domain={[0, 100]} tick={{ fill: "#6b7a99", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                <YAxis type="category" dataKey="category" tick={{ fill: "#6b7a99", fontSize: 11 }} width={120} />
                <Tooltip contentStyle={{ background: "#111a2e", border: "1px solid #263352" }} formatter={(v: any) => `${v}%`} />
                <Bar dataKey="otif_rate" fill="#38bdf8" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </AppShell>
  );
}
