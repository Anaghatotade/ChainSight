import React from "react";
import { LucideIcon } from "lucide-react";

interface Props {
  label: string;
  value: string;
  sublabel?: string;
  icon: LucideIcon;
  trend?: "up" | "down" | "neutral";
  accent?: string;
}

export default function KPICard({ label, value, sublabel, icon: Icon, accent = "text-brand-400" }: Props) {
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-500 font-semibold">{label}</p>
          <p className="text-2xl font-bold text-white mt-2">{value}</p>
          {sublabel && <p className="text-xs text-gray-500 mt-1">{sublabel}</p>}
        </div>
        <div className={`p-2 rounded-lg bg-white/5 ${accent}`}>
          <Icon size={20} />
        </div>
      </div>
    </div>
  );
}
