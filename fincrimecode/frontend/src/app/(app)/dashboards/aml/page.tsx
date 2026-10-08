"use client";

import { useState } from "react";

import { BarSeries, Donut } from "@/components/charts";
import { RunPicker, scopeQuery } from "@/components/Scope";
import { Card, CardBody, CardHeader, ErrorBox, Kpi, PageHeader, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtNum } from "@/lib/utils";
import Link from "next/link";

type Pair = { source?: number; target?: number; difference?: number };
type Count = { name: string; count: number };
type Aml = {
  kpis: { cases: Pair; high_risk_cases: Pair; sar_filed: Pair; watchlist_matches: Pair; failed_cases: number; open_exceptions: number };
  risk_categories: Count[];
  risk_categories_target: Count[];
  alert_types: Count[];
  case_status: Count[];
  failures_by_field: Count[];
};

const RISK_COLORS: Record<string, string> = { HIGH: "#DC3545", MEDIUM: "#FFC107", LOW: "#28A745", None: "#94A3B8" };

function sub(p: Pair) {
  const d = p.difference ?? 0;
  return <span className={d === 0 ? "text-success" : "text-danger"}>Source {fmtNum(p.source)} · diff {fmtNum(d)}</span>;
}

export default function AmlDashboard() {
  const { environment } = useSession();
  const [runId, setRunId] = useState<number | "">("");
  const { data, error, loading } = useApi<Aml>(`/api/dashboard/aml${scopeQuery(environment, runId)}`);

  const riskCompare = data
    ? Array.from(new Set([...data.risk_categories, ...data.risk_categories_target].map((r) => r.name))).map((name) => ({
        name,
        source: data.risk_categories.find((r) => r.name === name)?.count ?? 0,
        target: data.risk_categories_target.find((r) => r.name === name)?.count ?? 0,
      }))
    : [];

  return (
    <>
      <PageHeader title="AML Dashboard" subtitle="Alerts, cases, risk ratings and watchlist matches" actions={<RunPicker value={runId} onChange={setRunId} />} />
      <ErrorBox error={error} />
      {loading && !data && <Spinner />}
      {data && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-5">
            <Kpi label="AML cases (target)" value={fmtNum(data.kpis.cases.target)} sub={sub(data.kpis.cases)} />
            <Kpi label="High-risk cases" value={fmtNum(data.kpis.high_risk_cases.target)} sub={sub(data.kpis.high_risk_cases)} tone="danger" />
            <Kpi label="SARs filed" value={fmtNum(data.kpis.sar_filed.target)} sub={sub(data.kpis.sar_filed)} tone="secondary" />
            <Kpi label="Watchlist matches" value={fmtNum(data.kpis.watchlist_matches.target)} sub={sub(data.kpis.watchlist_matches)} tone="warning" />
            <Kpi
              label="Failed AML cases"
              value={<Link href="/exceptions?domain=aml" className="hover:underline">{fmtNum(data.kpis.failed_cases)}</Link>}
              sub={`${data.kpis.open_exceptions} open exceptions`}
              tone="danger"
            />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader title="Risk rating: source vs target" subtitle="Risk ratings must be preserved through migration" />
              <CardBody>
                <BarSeries
                  data={riskCompare}
                  series={[
                    { key: "source", label: "Source", color: "#004C7F" },
                    { key: "target", label: "Target", color: "#0070AD" },
                  ]}
                  height={260}
                />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Migration failures by field" />
              <CardBody>
                <BarSeries data={data.failures_by_field} series={[{ key: "count", label: "Exceptions", color: "#DC3545" }]} layout="vertical" height={260} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Alert types" />
              <CardBody>
                <Donut data={data.alert_types} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Case status (target)" />
              <CardBody>
                <Donut data={data.case_status} colors={RISK_COLORS} />
              </CardBody>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
