"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    const token = typeof window !== "undefined" ? sessionStorage.getItem("chainsight_token") : null;
    router.replace(token ? "/dashboard" : "/login");
  }, [router]);
  return null;
}
