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
