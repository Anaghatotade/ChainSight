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
