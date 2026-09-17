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
