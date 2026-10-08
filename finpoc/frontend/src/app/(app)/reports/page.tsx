"use client";

import { Download, FileArchive, FileSpreadsheet, FileText } from "lucide-react";
import { useEffect, useState } from "react";

import { RunPicker, useRuns } from "@/components/Scope";
import { Badge, Button, Card, CardBody, CardHeader, Empty, ErrorBox, PageHeader, Spinner, Table, Td, Th } from "@/components/ui";
import { api, qs, ReportItem } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { fmtDate, fmtNum, label } from "@/lib/utils";

type ReportType = { type: string; format: string; title: string; allowed: boolean };

const ICON: Record<string, typeof FileText> = { pdf: FileText, xlsx: FileSpreadsheet, zip: FileArchive };
const DESCRIPTION: Record<string, string> = {
  BUSINESS_RECONCILIATION: "Level 1/2/3 results, rule outcomes and exception summary per domain.",
  MIGRATION_SUMMARY: "Run metadata, volumes, progress and reconciliation percentage.",
  COMPLIANCE: "AML, KYC and sanctions reconciliation evidence for compliance review.",
  MANAGEMENT_SUMMARY: "Executive narrative, KPIs and sign-off status.",
  DETAILED_MISMATCH: "Every mismatched record and field with source/target values.",
  AUDIT_PACK: "Migration evidence, exception log, approval log and audit trail with SHA-256 manifest.",
};

export default function ReportsPage() {
  const { data: runs } = useRuns();
  const [runId, setRunId] = useState<number | "">("");
  const types = useApi<ReportType[]>("/api/reports/types");
  const reports = useApi<ReportItem[]>(`/api/reports${qs({ run_id: runId || undefined })}`);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!runId && runs?.length) setRunId(runs[0].id);
  }, [runs, runId]);

  const generate = async (type: string) => {
    if (!runId) return;
    setBusy(type);
    setError(null);
    try {
      const report = await api.post<ReportItem>("/api/reports", { run_id: runId, report_type: type });
      await api.download(`/api/reports/${report.id}/download`, report.filename);
      reports.reload();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader title="Reports" subtitle="Regulator-ready reports and audit evidence" actions={<RunPicker value={runId} onChange={setRunId} allowAll={false} />} />
      <ErrorBox error={error} />
      <div className="mb-5 mt-2 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(types.data || []).map((t) => {
          const Icon = ICON[t.format] || FileText;
          return (
            <Card key={t.type} className={t.allowed ? "" : "opacity-60"}>
              <CardBody className="flex h-full flex-col">
                <div className="flex items-start gap-3">
                  <div className="rounded-md bg-primary-50 p-2 text-primary">
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-secondary">{t.title}</span>
                      <Badge>{t.format.toUpperCase()}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">{DESCRIPTION[t.type]}</p>
                  </div>
                </div>
                <div className="mt-auto pt-3">
                  <Button size="sm" className="w-full" disabled={!t.allowed || !runId} loading={busy === t.type} onClick={() => generate(t.type)}>
                    {t.allowed ? "Generate & download" : "Not permitted for your role"}
                  </Button>
                </div>
              </CardBody>
            </Card>
          );
        })}
      </div>
      <Card>
        <CardHeader title="Generated reports" subtitle="Stored with SHA-256 hash for evidence integrity" />
        {reports.loading && !reports.data ? (
          <Spinner />
        ) : !reports.data?.length ? (
          <Empty>No reports generated yet.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>File</Th>
                <Th>Type</Th>
                <Th>Run</Th>
                <Th className="text-right">Size</Th>
                <Th>SHA-256</Th>
                <Th>Generated</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {reports.data.map((r) => (
                <tr key={r.id}>
                  <Td className="font-medium">{r.filename}</Td>
                  <Td className="text-xs">{label(r.report_type)}</Td>
                  <Td>#{r.run_id}</Td>
                  <Td className="tabular text-right text-xs">{fmtNum(r.size_bytes / 1024, 1)} KB</Td>
                  <Td className="font-mono text-[11px] text-slate-500">{r.sha256.slice(0, 16)}…</Td>
                  <Td className="text-xs text-slate-500">
                    {r.created_by} · {fmtDate(r.created_at)}
                  </Td>
                  <Td>
                    <Button size="sm" variant="ghost" onClick={() => api.download(`/api/reports/${r.id}/download`, r.filename)}>
                      <Download className="h-3.5 w-3.5" />
                    </Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
