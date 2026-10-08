"use client";

import { useState } from "react";

import { BarSeries, Donut } from "@/components/charts";
import { RunPicker, scopeQuery } from "@/components/Scope";
import { Card, CardBody, CardHeader, ErrorBox, Kpi, PageHeader, Spinner, Table, Td, Th } from "@/components/ui";
import { FieldDiff } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtCompact, fmtNum, label } from "@/lib/utils";
import Link from "next/link";

type Pair = { source?: number; target?: number; difference?: number };
type Finance = {
  kpis: {
    accounts: Pair;
    total_current_balance: Pair;
    financial_variance: number;
    variance_exceptions: number;
    debit_total: Pair;
    credit_total: Pair;
  };
  ledger_comparison: ({ name: string } & Pair)[];
  debit_credit: ({ name: string } & Pair)[];
  transaction_status: ({ name: string } & Pair)[];
  top_variances: { run_id: number; account_id: string; total_abs_variance: number; fields: FieldDiff[] }[];
  variance_by_root_cause: { name: string; count: number; value?: number }[];
};

const SRC_TGT = [
  { key: "source", label: "Source", color: "#004C7F" },
  { key: "target", label: "Target", color: "#0070AD" },
];

function diffSub(p: Pair) {
  const d = p.difference ?? 0;
  return <span className={d === 0 ? "text-success" : "text-danger"}>Target − source: {fmtCompact(d)}</span>;
}

export default function FinanceDashboard() {
  const { environment } = useSession();
  const [runId, setRunId] = useState<number | "">("");
  const { data, error, loading } = useApi<Finance>(`/api/dashboard/finance${scopeQuery(environment, runId)}`);

  return (
    <>
      <PageHeader title="Finance Dashboard" subtitle="Balance reconciliation, ledger comparison and financial variance" actions={<RunPicker value={runId} onChange={setRunId} />} />
      <ErrorBox error={error} />
      {loading && !data && <Spinner />}
      {data && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-5">
            <Kpi label="Accounts (target)" value={fmtNum(data.kpis.accounts.target)} sub={diffSub(data.kpis.accounts)} />
            <Kpi label="Current balance (target)" value={<span title={fmtNum(data.kpis.total_current_balance.target, 2)}>{fmtCompact(data.kpis.total_current_balance.target)}</span>} sub={diffSub(data.kpis.total_current_balance)} tone="secondary" />
            <Kpi label="Financial variance" value={<span title={fmtNum(data.kpis.financial_variance, 2)}>{fmtCompact(data.kpis.financial_variance)}</span>} sub={`${data.kpis.variance_exceptions} balance variance exceptions`} tone="danger" />
            <Kpi label="Debit total (target)" value={<span title={fmtNum(data.kpis.debit_total.target, 2)}>{fmtCompact(data.kpis.debit_total.target)}</span>} sub={diffSub(data.kpis.debit_total)} tone="warning" />
            <Kpi label="Credit total (target)" value={<span title={fmtNum(data.kpis.credit_total.target, 2)}>{fmtCompact(data.kpis.credit_total.target)}</span>} sub={diffSub(data.kpis.credit_total)} tone="success" />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader title="Ledger comparison" subtitle="Level 1 control totals per balance type" />
              <CardBody>
                <BarSeries data={data.ledger_comparison} series={SRC_TGT} height={280} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Variance by root cause" subtitle="Absolute variance value" />
              <CardBody>
                <Donut data={data.variance_by_root_cause.map((r) => ({ name: label(r.name), count: r.value ?? r.count }))} height={280} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Debit vs credit totals" />
              <CardBody>
                <BarSeries data={data.debit_credit} series={SRC_TGT} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Transactions by status" subtitle="Posted / pending / reversed counts" />
              <CardBody>
                <BarSeries data={data.transaction_status} series={SRC_TGT} />
              </CardBody>
            </Card>
          </div>
          <Card>
            <CardHeader title="Top balance variances" subtitle="Accounts with the highest absolute variance" />
            <Table>
              <thead>
                <tr>
                  <Th>Account</Th>
                  <Th>Run</Th>
                  <Th className="text-right">Total abs. variance</Th>
                  <Th>Fields</Th>
                </tr>
              </thead>
              <tbody>
                {data.top_variances.map((t) => (
                  <tr key={`${t.run_id}-${t.account_id}`} className="hover:bg-slate-50">
                    <Td>
                      <Link className="font-medium text-primary hover:underline" href={`/reconciliation?run=${t.run_id}&domain=balance&key=${t.account_id}`}>
                        {t.account_id}
                      </Link>
                    </Td>
                    <Td>#{t.run_id}</Td>
                    <Td className="tabular text-right font-medium text-danger">{fmtNum(t.total_abs_variance, 2)}</Td>
                    <Td className="text-xs text-slate-600">
                      {t.fields.map((f) => `${f.field}: ${fmtNum(Number(f.source), 2)} → ${fmtNum(Number(f.target), 2)}`).join(" · ")}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}
