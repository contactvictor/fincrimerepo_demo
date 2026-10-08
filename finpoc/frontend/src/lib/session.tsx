"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, Me, tokenStore } from "./api";

type Session = {
  user: Me | null;
  environment: string;
  setEnvironment: (env: string) => void;
  can: (permission: string) => boolean;
  canDomain: (domain: string) => boolean;
  logout: () => void;
};

const SessionContext = createContext<Session | null>(null);
const ENV_KEY = "fcr_env";

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<Me | null>(null);
  const [environment, setEnv] = useState<string>("");

  useEffect(() => {
    setEnv(window.localStorage.getItem(ENV_KEY) || "");
    if (!tokenStore.get()) {
      router.replace("/login");
      return;
    }
    api.get<Me>("/api/auth/me").then(setUser).catch(() => router.replace("/login"));
  }, [router]);

  const setEnvironment = useCallback((env: string) => {
    window.localStorage.setItem(ENV_KEY, env);
    setEnv(env);
  }, []);

  const can = useCallback(
    (permission: string) => !!user && (user.permissions.includes("*") || user.permissions.includes(permission)),
    [user],
  );
  const canDomain = useCallback(
    (domain: string) => !!user && (!user.domains || user.domains.includes(domain.toLowerCase())),
    [user],
  );

  const logout = useCallback(() => {
    tokenStore.clear();
    router.replace("/login");
  }, [router]);

  return (
    <SessionContext.Provider value={{ user, environment, setEnvironment, can, canDomain, logout }}>{children}</SessionContext.Provider>
  );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}
