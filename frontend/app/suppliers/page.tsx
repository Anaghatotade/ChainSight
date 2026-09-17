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
