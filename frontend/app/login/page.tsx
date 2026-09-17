"use client";

import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Boxes, Loader2 } from "lucide-react";

export default function LoginPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("analyst@chainsight.io");
  const [password, setPassword] = useState("Analyst123!");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("analyst");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, fullName, role);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-3 mb-8 justify-center">
          <div className="bg-brand-500/20 p-3 rounded-xl">
            <Boxes className="text-brand-400" size={28} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">ChainSight</h1>
            <p className="text-sm text-gray-400">Decision Support Platform</p>
          </div>
        </div>

        <div className="card p-8">
          <div className="flex mb-6 border border-[#263352] rounded-lg overflow-hidden">
            <button
              className={`flex-1 py-2 text-sm font-semibold ${mode === "login" ? "bg-brand-600 text-white" : "text-gray-400"}`}
              onClick={() => setMode("login")}
            >
              Sign In
            </button>
            <button
              className={`flex-1 py-2 text-sm font-semibold ${mode === "register" ? "bg-brand-600 text-white" : "text-gray-400"}`}
              onClick={() => setMode("register")}
            >
              Create Account
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === "register" && (
              <div>
                <label className="block text-sm text-gray-400 mb-1">Full Name</label>
                <input className="input w-full" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
              </div>
            )}
            <div>
              <label className="block text-sm text-gray-400 mb-1">Email</label>
              <input type="email" className="input w-full" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Password</label>
              <input type="password" className="input w-full" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
            </div>
            {mode === "register" && (
              <div>
                <label className="block text-sm text-gray-400 mb-1">Role</label>
                <select className="input w-full" value={role} onChange={(e) => setRole(e.target.value)}>
                  <option value="analyst">Analyst</option>
                  <option value="admin">Admin</option>
                  <option value="viewer">Viewer</option>
                </select>
              </div>
            )}

            {error && <p className="text-sm text-red-400">{error}</p>}

            <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2">
              {loading && <Loader2 className="animate-spin" size={16} />}
              {mode === "login" ? "Sign In" : "Create Account"}
            </button>
          </form>

          <div className="mt-6 pt-4 border-t border-[#1e2a44] text-xs text-gray-500">
            <p className="font-semibold text-gray-400 mb-1">Demo accounts (seeded automatically):</p>
            <p>admin@chainsight.io / Admin123!</p>
            <p>analyst@chainsight.io / Analyst123!</p>
            <p>viewer@chainsight.io / Viewer123!</p>
          </div>
        </div>
      </div>
    </div>
  );
}
