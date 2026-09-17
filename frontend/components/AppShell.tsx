"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import {
  LayoutDashboard, Truck, Boxes, TrendingUp, AlertTriangle,
  ShieldAlert, FlaskConical, ListChecks, LogOut,
} from "lucide-react";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/suppliers", label: "Suppliers", icon: Truck },
  { href: "/inventory", label: "Inventory", icon: Boxes },
  { href: "/forecasting", label: "Demand Forecast", icon: TrendingUp },
  { href: "/anomalies", label: "Anomalies", icon: AlertTriangle },
  { href: "/risk", label: "Stockout Risk", icon: ShieldAlert },
  { href: "/simulator", label: "What-If Simulator", icon: FlaskConical },
  { href: "/recommendations", label: "Recommendations", icon: ListChecks },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface text-gray-400">
        Loading...
      </div>
    );
  }

  return (
    <div className="min-h-screen flex bg-surface">
      <aside className="w-64 shrink-0 border-r border-[#1e2a44] flex flex-col">
        <div className="p-5 border-b border-[#1e2a44]">
          <h1 className="text-white font-bold text-lg leading-tight">ChainSight</h1>
          <p className="text-xs text-gray-500 mt-1">Decision Support Platform</p>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname?.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  active ? "bg-brand-600 text-white" : "text-gray-400 hover:bg-[#182238] hover:text-white"
                }`}
              >
                <Icon size={18} />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="p-4 border-t border-[#1e2a44]">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-white font-medium">{user.full_name}</p>
              <p className="text-xs text-gray-500 capitalize">{user.role}</p>
            </div>
            <button onClick={logout} className="text-gray-400 hover:text-red-400" title="Log out">
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>
      <main className="flex-1 overflow-x-hidden">
        <div className="p-6 max-w-[1600px] mx-auto">{children}</div>
      </main>
    </div>
  );
}
