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
