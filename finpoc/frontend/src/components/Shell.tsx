"use client";

import {
  Bell, Bot, ClipboardCheck, FileText, Gauge, Landmark, LogOut, PlayCircle, Scale, Search, Settings, ShieldAlert,
  ShieldCheck, TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge, Select, Spinner } from "@/components/ui";
import { api, ExceptionItem } from "@/lib/api";
import { useSession } from "@/lib/session";
import { cn, label } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Executive Dashboard", icon: Gauge, perm: "dashboard:read" },
  { href: "/dashboards/finance", label: "Finance Dashboard", icon: Landmark, perm: "dashboard:read" },
  { href: "/dashboards/aml", label: "AML Dashboard", icon: ShieldAlert, perm: "dashboard:read" },
  { href: "/dashboards/compliance", label: "Compliance Dashboard", icon: ClipboardCheck, perm: "dashboard:read" },
  { href: "/runs", label: "Migration Runs", icon: PlayCircle, perm: "runs:read" },
  { href: "/reconciliation", label: "Reconciliation", icon: Scale, perm: "recon:read" },
  { href: "/exceptions", label: "Exceptions", icon: TriangleAlert, perm: "exceptions:read" },
  { href: "/reports", label: "Reports", icon: FileText, perm: "reports:read" },
  { href: "/assistant", label: "AI Assistant", icon: Bot, perm: "ai:use" },
  { href: "/admin", label: "Administration", icon: Settings, perm: "dashboard:read" },
];

const ENVIRONMENTS = ["DEV", "SIT", "UAT", "PRE_PROD", "PROD"];

type SearchResult = {
  runs: { id: number; name: string }[];
  exceptions: { code: string; domain: string; description: string }[];
  records: { run_id: number; domain: string; record_key: string; status: string }[];
};

function GlobalSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) {
      setResult(null);
      return;
    }
    const t = setTimeout(() => {
      api.get<SearchResult>(`/api/search?q=${encodeURIComponent(q.trim())}`).then(setResult).catch(() => setResult(null));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const go = (href: string) => {
    setQ("");
    setResult(null);
    router.push(href);
  };
  const empty = result && !result.runs.length && !result.exceptions.length && !result.records.length;

  return (
    <div className="relative w-80">
      <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search runs, exceptions, account / customer IDs"
        className="h-9 w-full rounded-md border border-slate-200 bg-slate-50 pl-8 pr-3 text-sm outline-none focus:border-primary focus:bg-white"
      />
      {result && (
        <div className="absolute z-40 mt-1 max-h-96 w-[28rem] overflow-y-auto rounded-md border bg-white p-2 text-sm shadow-lg">
          {empty && <div className="p-2 text-slate-500">No matches</div>}
          {result.runs.map((r) => (
            <button key={`r${r.id}`} className="block w-full rounded px-2 py-1.5 text-left hover:bg-slate-50" onClick={() => go(`/runs/${r.id}`)}>
              <Badge>Run</Badge> <span className="ml-1">{r.name}</span>
            </button>
          ))}
          {result.exceptions.map((e) => (
            <button key={e.code} className="block w-full rounded px-2 py-1.5 text-left hover:bg-slate-50" onClick={() => go(`/exceptions?code=${e.code}`)}>
              <Badge value="HIGH">{e.code}</Badge> <span className="ml-1 text-slate-600">{e.description.slice(0, 70)}</span>
            </button>
          ))}
          {result.records.map((r) => (
            <button
              key={`${r.run_id}-${r.domain}-${r.record_key}`}
              className="block w-full rounded px-2 py-1.5 text-left hover:bg-slate-50"
              onClick={() => go(`/reconciliation?run=${r.run_id}&domain=${r.domain}&key=${r.record_key}`)}
            >
              <Badge value={r.status} /> <span className="ml-1">{r.domain} · {r.record_key}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Notifications() {
  const [data, setData] = useState<{ unread: number; items: ExceptionItem[] } | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    api.get<{ unread: number; items: ExceptionItem[] }>("/api/notifications").then(setData).catch(() => undefined);
  }, []);
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} className="relative rounded-md p-2 text-slate-500 hover:bg-slate-100" aria-label="Notifications">
        <Bell className="h-5 w-5" />
        {!!data?.unread && (
          <span className="absolute -right-0.5 -top-0.5 rounded-full bg-danger px-1.5 text-[10px] font-semibold text-white">{data.unread}</span>
        )}
      </button>
      {open && data && (
        <div className="absolute right-0 z-40 mt-1 w-96 rounded-md border bg-white shadow-lg">
          <div className="border-b px-3 py-2 text-xs font-semibold text-slate-500">Unassigned critical exceptions</div>
          {data.items.length === 0 && <div className="p-3 text-sm text-slate-500">Nothing needs attention.</div>}
          {data.items.map((e) => (
            <Link key={e.code} href={`/exceptions?code=${e.code}`} onClick={() => setOpen(false)} className="block border-b px-3 py-2 text-sm hover:bg-slate-50">
              <div className="flex items-center gap-2">
                <Badge value="CRITICAL">{e.code}</Badge>
                <span className="text-xs text-slate-500">{e.domain.toUpperCase()}</span>
              </div>
              <div className="mt-0.5 text-slate-600">{e.description}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, can, logout, environment, setEnvironment } = useSession();

  if (!user) return <Spinner label="Signing in..." />;

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 flex w-60 flex-col bg-secondary text-white">
        <div className="flex h-14 items-center gap-2 border-b border-white/10 px-4 font-semibold">
          <ShieldCheck className="h-5 w-5" /> FinCrime Recon
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
          {NAV.filter((n) => can(n.perm)).map((n) => {
            const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition",
                  active ? "bg-primary text-white" : "text-white/75 hover:bg-white/10 hover:text-white",
                )}
              >
                <n.icon className="h-4 w-4" /> {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-white/10 p-3 text-xs">
          <div className="font-medium">{user.full_name}</div>
          <div className="text-white/60">{label(user.role)}</div>
          <button onClick={logout} className="mt-2 flex items-center gap-1.5 text-white/70 hover:text-white">
            <LogOut className="h-3.5 w-3.5" /> Sign out
          </button>
        </div>
      </aside>
      <div className="ml-60 flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-4 border-b bg-white px-6">
          <GlobalSearch />
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-500">
              Environment
              <Select value={environment} onChange={(e) => setEnvironment(e.target.value)} className="h-8 text-xs">
                <option value="">All</option>
                {ENVIRONMENTS.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </Select>
            </label>
            <Notifications />
          </div>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
