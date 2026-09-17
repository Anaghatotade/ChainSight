import React from "react";
import { Loader2, AlertCircle } from "lucide-react";

export function Badge({ level }: { level: string }) {
  const cls = `badge badge-${level}`;
  return <span className={cls}>{level.charAt(0).toUpperCase() + level.slice(1)}</span>;
}

export function LoadingState({ label = "Loading data..." }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-gray-400 py-16 justify-center">
      <Loader2 className="animate-spin" size={18} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 text-red-400 py-16 justify-center">
      <AlertCircle size={18} />
      <span>{message}</span>
    </div>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-6">
      <div>
        <h1 className="text-2xl font-bold text-white">{title}</h1>
        {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
