"use client";

import { ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, ErrorBox, Field, Input } from "@/components/ui";
import { api, tokenStore } from "@/lib/api";

const DEMO = [
  { username: "admin", role: "Administrator" },
  { username: "analyst", role: "Business Analyst" },
  { username: "finance", role: "Finance User" },
  { username: "compliance", role: "Compliance User" },
  { username: "auditor", role: "Auditor" },
];

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("Passw0rd!");
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.login(username, password);
      tokenStore.set(res.access_token);
      router.replace("/");
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen">
      <div className="hidden w-1/2 flex-col justify-between bg-gradient-to-br from-secondary to-primary p-12 text-white lg:flex">
        <div className="flex items-center gap-2 text-lg font-semibold">
          <ShieldCheck className="h-6 w-6" /> FinCrime Recon
        </div>
        <div>
          <h1 className="text-3xl font-semibold leading-tight">Balance Migration &amp; Reconciliation Platform</h1>
          <p className="mt-4 max-w-md text-white/80">
            Automated Level 1/2/3 reconciliation across customer, account, balance, transaction, AML, KYC, sanctions and
            audit data — with exception workflow, business sign-off and regulator-ready evidence.
          </p>
        </div>
        <p className="text-xs text-white/60">Single sign-on via Azure Entra ID is supported in production deployments.</p>
      </div>
      <div className="flex flex-1 items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-4">
          <div>
            <h2 className="text-xl font-semibold text-secondary">Sign in</h2>
            <p className="text-sm text-slate-500">Use a demo account below.</p>
          </div>
          <Field label="Username">
            <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </Field>
          <Field label="Password">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </Field>
          <ErrorBox error={error} />
          <Button type="submit" className="w-full" loading={loading}>
            Sign in
          </Button>
          <div className="rounded-md border border-slate-200 bg-white p-3">
            <div className="mb-2 text-xs font-medium text-slate-500">Demo accounts (password: Passw0rd!)</div>
            <div className="grid grid-cols-2 gap-1.5">
              {DEMO.map((d) => (
                <button
                  type="button"
                  key={d.username}
                  onClick={() => {
                    setUsername(d.username);
                    setPassword("Passw0rd!");
                  }}
                  className={`rounded border px-2 py-1 text-left text-xs hover:border-primary ${
                    username === d.username ? "border-primary bg-primary-50" : "border-slate-200"
                  }`}
                >
                  <div className="font-medium text-secondary">{d.username}</div>
                  <div className="text-slate-500">{d.role}</div>
                </button>
              ))}
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
