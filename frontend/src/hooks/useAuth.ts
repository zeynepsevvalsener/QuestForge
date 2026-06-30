"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { clearToken, getToken } from "@/lib/api";

export function useAuth(requireAuth = true) {
  const router = useRouter();
  const [token, setTokenState] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const t = getToken();
    setTokenState(t);
    setReady(true);
    if (requireAuth && !t) {
      router.replace("/login");
    }
  }, [requireAuth, router]);

  const logout = useCallback(() => {
    clearToken();
    setTokenState(null);
    router.replace("/login");
  }, [router]);

  return { token, ready, isAuthenticated: !!token, logout };
}
