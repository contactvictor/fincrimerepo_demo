"use client";

import { useState } from "react";

import { BarSeries, Donut } from "@/components/charts";
import { RunPicker, scopeQuery } from "@/components/Scope";
import { Card, CardBody, CardHeader, ErrorBox, Kpi, PageHeader, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtNum, label } from "@/lib/utils";

type Pair = { source?: number; target?: number; difference?: number };
type Count = { name: string; count: number };
type Compliance = {
  kpis: { kyc_records: Pair; pep_customers: Pair; missing_documents: number; sanctions_matches: Pair; open_matches: Pair; open_exceptions: number };
  kyc_status: Count[];
  risk_classification: Count[];
  pep_classification: Count[];
  sanctions_status: Count[];
  screening_findings: Count[];
  exceptions_by_field: Count[];
};

function sub(p: Pair) {
  const d = p.difference ?? 0;
  return <span className={d === 0 ? "text-success" : "text-danger"}>Source {fmtNum(p.source)} · diff {fmtNum(d)}</span>;
}

export default function ComplianceDashboard() {
  const { environment } = useSession();
  const [runId, setRunId] = useState<number | "">("");
  const { data, error, loading } = useApi<Compliance>(`/api/dashboard/compliance${scopeQuery(environment, runId)}`);

  return (
    <>
      <PageHeader title="Compliance Dashboard" subtitle="KYC status, PEP classification, sanctions screening and documents" actions={<RunPicker value={runId} onChange={setRunId} />} />
      <ErrorBox error={error} />
      {loading && !data && <Spinner />}
      {data && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-5">
            <Kpi label="KYC records (target)" value={fmtNum(data.kpis.kyc_records.target)} sub={sub(data.kpis.kyc_records)} />
            <Kpi label="PEP customers" value={fmtNum(data.kpis.pep_customers.target)} sub={sub(data.kpis.pep_customers)} tone="warning" />
            <Kpi label="Missing documents" value={fmtNum(data.kpis.missing_documents)} sub="Document count mismatches" tone="danger" />
            <Kpi label="Sanctions matches" value={fmtNum(data.kpis.sanctions_matches.target)} sub={sub(data.kpis.sanctions_matches)} tone="secondary" />
            <Kpi label="Open sanctions matches" value={fmtNum(data.kpis.open_matches.target)} sub={sub(data.kpis.open_matches)} tone="danger" />
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader title="KYC status" />
              <CardBody>
                <Donut data={data.kyc_status} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Risk classification" />
              <CardBody>
                <Donut data={data.risk_classification} colors={{ HIGH: "#DC3545", MEDIUM: "#FFC107", LOW: "#28A745" }} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="PEP classification" />
              <CardBody>
                <Donut data={data.pep_classification} colors={{ PEP: "#DC3545", "Non-PEP": "#0070AD" }} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Sanctions match status" />
              <CardBody>
                <Donut data={data.sanctions_status} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Screening findings" />
              <CardBody>
                <Donut data={data.screening_findings.map((f) => ({ ...f, name: label(f.name) }))} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Exceptions by field" subtitle={`${data.kpis.open_exceptions} open KYC / sanctions exceptions`} />
              <CardBody>
                <BarSeries data={data.exceptions_by_field} series={[{ key: "count", label: "Exceptions", color: "#DC3545" }]} layout="vertical" height={220} />
              </CardBody>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
