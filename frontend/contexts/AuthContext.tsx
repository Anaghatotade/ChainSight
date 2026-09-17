"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, User } from "@/lib/api";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string, role: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const raw = typeof window !== "undefined" ? sessionStorage.getItem("chainsight_user") : null;
    if (raw) {
      try {
        setUser(JSON.parse(raw));
      } catch {
        // ignore
      }
    }
    setLoading(false);
  }, []);

  const persist = (token: string, u: User) => {
    sessionStorage.setItem("chainsight_token", token);
    sessionStorage.setItem("chainsight_user", JSON.stringify(u));
    setUser(u);
  };

  const login = async (email: string, password: string) => {
    const resp = await api.post("/api/v1/auth/login", { email, password });
    persist(resp.data.access_token, resp.data.user);
    router.push("/dashboard");
  };

  const register = async (email: string, password: string, fullName: string, role: string) => {
    const resp = await api.post("/api/v1/auth/register", {
      email, password, full_name: fullName, role,
    });
    persist(resp.data.access_token, resp.data.user);
    router.push("/dashboard");
  };

  const logout = () => {
    sessionStorage.removeItem("chainsight_token");
    sessionStorage.removeItem("chainsight_user");
    setUser(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
