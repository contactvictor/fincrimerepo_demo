"use client";

import { Activity, AlertTriangle, CheckCircle2, Database, FileCheck2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { BarSeries, Donut, Heatmap, SEVERITY_COLORS, STATUS_COLORS, Trend } from "@/components/charts";
import { RunPicker, scopeQuery } from "@/components/Scope";
import { Badge, Card, CardBody, CardHeader, ErrorBox, Kpi, PageHeader, Progress, Spinner, Table, Td, Th } from "@/components/ui";
import { DomainStat } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { DOMAIN_LABEL, DOMAINS, fmtNum, fmtPct, label } from "@/lib/utils";

type Executive = {
  kpis: {
    migration_progress: number;
    runs: number;
    runs_completed: number;
    records_processed: number;
    reconciliation_pct: number;
    exceptions: number;
    open_exceptions: number;
    critical_open: number;
    signoff_approved: number;
  };
  cards: Record<string, DomainStat>;
  runs: {
    id: number;
    name: string;
    status: string;
    environment: string;
    progress: number;
    reconciliation_pct: number;
    records_processed: number;
    signoff_status: string;
    source_system: string;
    target_system: string;
  }[];
  errors_by_domain: { name: string; count: number; open: number }[];
  heatmap: { domain: string; L1: number | null; L2: number | null; L3: number | null }[];
  exception_trend: { date: string; detected: number; resolved: number }[];
  signoffs: { run_id: number; run_name: string; status: string; areas: Record<string, string> }[];
  by_severity: { name: string; count: number }[];
  by_root_cause: { name: string; count: number }[];
  by_status: { name: string; count: number }[];
};

export default function ExecutiveDashboard() {
  const { environment } = useSession();
  const [runId, setRunId] = useState<number | "">("");
  const { data, error, loading } = useApi<Executive>(`/api/dashboard/executive${scopeQuery(environment, runId)}`);

  return (
    <>
      <PageHeader
        title="Executive Dashboard"
        subtitle="Migration progress, reconciliation quality and business sign-off status"
        actions={<RunPicker value={runId} onChange={setRunId} />}
      />
      <ErrorBox error={error} />
      {loading && !data && <Spinner />}
      {data && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-5">
            <Kpi label="Migration progress" value={fmtPct(data.kpis.migration_progress, 1)} sub={`${data.kpis.runs_completed}/${data.kpis.runs} runs completed`} icon={<Activity />} />
            <Kpi label="Records processed" value={fmtNum(data.kpis.records_processed)} sub="Across all domains" icon={<Database />} tone="secondary" />
            <Kpi
              label="Reconciliation %"
              value={fmtPct(data.kpis.reconciliation_pct)}
              sub="Records matched (Level 2)"
              tone={data.kpis.reconciliation_pct >= 99.9 ? "success" : "warning"}
              icon={<CheckCircle2 />}
            />
            <Kpi
              label="Open exceptions"
              value={fmtNum(data.kpis.open_exceptions)}
              sub={`${data.kpis.critical_open} critical · ${data.kpis.exceptions} total`}
              tone="danger"
              icon={<AlertTriangle />}
            />
            <Kpi label="Sign-off approved" value={`${data.kpis.signoff_approved}/${data.kpis.runs}`} sub="Runs fully signed off" tone="success" icon={<FileCheck2 />} />
          </div>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {DOMAINS.map((d) => {
              const c = data.cards[d];
              if (!c) return null;
              return (
                <Link key={d} href={`/reconciliation?domain=${d}${runId ? `&run=${runId}` : ""}`}>
                  <Card className="p-4 transition hover:border-primary hover:shadow">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-secondary">{DOMAIN_LABEL[d]}</span>
                      {c.open_exceptions > 0 ? <Badge value="HIGH">{c.open_exceptions} open</Badge> : <Badge value="MATCHED">Clean</Badge>}
                    </div>
                    <div className="tabular mt-2 text-xl font-semibold text-secondary">{c.match_pct === null ? "-" : fmtPct(c.match_pct)}</div>
                    <Progress value={c.match_pct ?? 0} />
                    <div className="tabular mt-2 grid grid-cols-3 gap-1 text-[11px] text-slate-500">
                      <span>Src {fmtNum(c.source_count)}</span>
                      <span>Tgt {fmtNum(c.target_count)}</span>
                      <span>Diff {fmtNum(c.MISMATCHED + c.MISSING_IN_TARGET + c.MISSING_IN_SOURCE)}</span>
                    </div>
                  </Card>
                </Link>
              );
            })}
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-1">
              <CardHeader title="Reconciliation heatmap" subtitle="Pass rate by domain and reconciliation level" />
              <CardBody>
                <Heatmap rows={data.heatmap} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Exceptions by domain" subtitle="Total vs still open" />
              <CardBody>
                <BarSeries
                  data={data.errors_by_domain.map((e) => ({ ...e, name: DOMAIN_LABEL[e.name] || e.name }))}
                  series={[
                    { key: "count", label: "Total", color: "#004C7F" },
                    { key: "open", label: "Open", color: "#DC3545" },
                  ]}
                  height={280}
                />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Exception trend" subtitle="Detected vs resolved, last 21 days" />
              <CardBody>
                <Trend data={data.exception_trend} height={280} />
              </CardBody>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader title="Severity" />
              <CardBody>
                <Donut data={data.by_severity} colors={SEVERITY_COLORS} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Workflow status" />
              <CardBody>
                <Donut data={data.by_status} colors={STATUS_COLORS} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Root cause" />
              <CardBody>
                <Donut data={data.by_root_cause.map((r) => ({ ...r, name: label(r.name) }))} />
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader title="Migration runs & business sign-off" />
            <Table>
              <thead>
                <tr>
                  <Th>Run</Th>
                  <Th>Env</Th>
                  <Th>Source → Target</Th>
                  <Th>Status</Th>
                  <Th className="w-40">Progress</Th>
                  <Th className="text-right">Records</Th>
                  <Th className="text-right">Recon %</Th>
                  <Th>Finance</Th>
                  <Th>AML</Th>
                  <Th>Compliance</Th>
                  <Th>Operations</Th>
                  <Th>Sign-off</Th>
                </tr>
              </thead>
              <tbody>
                {data.runs.map((r) => {
                  const so = data.signoffs.find((s) => s.run_id === r.id);
                  return (
                    <tr key={r.id} className="hover:bg-slate-50">
                      <Td>
                        <Link href={`/runs/${r.id}`} className="font-medium text-primary hover:underline">
                          {r.name}
                        </Link>
                      </Td>
                      <Td>{r.environment}</Td>
                      <Td className="text-xs text-slate-600">
                        {r.source_system} → {r.target_system}
                      </Td>
                      <Td>
                        <Badge value={r.status} />
                      </Td>
                      <Td>
                        <Progress value={r.progress} tone="bg-primary" />
                        <div className="mt-0.5 text-[11px] text-slate-500">{fmtPct(r.progress, 0)}</div>
                      </Td>
                      <Td className="tabular text-right">{fmtNum(r.records_processed)}</Td>
                      <Td className="tabular text-right">{fmtPct(r.reconciliation_pct)}</Td>
                      {["FINANCE", "AML", "COMPLIANCE", "OPERATIONS"].map((a) => (
                        <Td key={a}>
                          <Badge value={so?.areas[a] || "PENDING"} />
                        </Td>
                      ))}
                      <Td>
                        <Badge value={r.signoff_status} />
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}
