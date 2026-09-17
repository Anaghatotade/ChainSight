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
