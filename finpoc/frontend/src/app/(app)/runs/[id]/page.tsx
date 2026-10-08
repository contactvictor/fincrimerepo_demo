"use client";

import { CheckCircle2, Play, Upload, XCircle } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import {
  Badge, Button, Card, CardBody, CardHeader, ErrorBox, Field, Input, Kpi, Modal, PageHeader, Progress, Select, Spinner, Table,
  Td, Textarea, Th,
} from "@/components/ui";
import { api, DomainStat, Meta, Run, RuleResult, SignOff } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { DOMAIN_LABEL, DOMAINS, fmtDate, fmtNum, fmtPct } from "@/lib/utils";

type RunDetail = {
  run: Run;
  domains: DomainStat[];
  rule_results: RuleResult[];
  signoffs: SignOff[];
  signoff_blockers: Record<string, number>;
};

const AREAS = ["FINANCE", "AML", "COMPLIANCE", "OPERATIONS"];

function LoadDataModal({ runId, open, onClose, onLoaded }: { runId: number; open: boolean; onClose: () => void; onLoaded: () => void }) {
  const { data: meta } = useApi<Meta>("/api/meta");
  const [mode, setMode] = useState<"file" | "sql">("file");
  const [domain, setDomain] = useState("customer");
  const [side, setSide] = useState("source");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [query, setQuery] = useState("SELECT * FROM customers");
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    setResult("");
    try {
      let res: { loaded: number };
      if (mode === "file") {
        const fd = new FormData();
        fd.set("domain", domain);
        fd.set("side", side);
        fd.set("replace", "true");
        fd.set("file", file as File);
        res = await api.form(`/api/runs/${runId}/upload`, fd);
      } else {
        res = await api.post(`/api/runs/${runId}/extract`, { domain, side, connector: "sql", url, query });
      }
      setResult(`Loaded ${fmtNum(res.loaded)} ${domain} records into ${side}.`);
      onLoaded();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Load source / target data">
      <div className="space-y-3">
        <div className="flex gap-2">
          <Button size="sm" variant={mode === "file" ? "primary" : "outline"} onClick={() => setMode("file")}>
            File (CSV / Parquet / JSON / flat)
          </Button>
          <Button size="sm" variant={mode === "sql" ? "primary" : "outline"} onClick={() => setMode("sql")}>
            SQL connector
          </Button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Domain">
            <Select className="w-full" value={domain} onChange={(e) => setDomain(e.target.value)}>
              {DOMAINS.map((d) => (
                <option key={d} value={d}>
                  {DOMAIN_LABEL[d]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Side">
            <Select className="w-full" value={side} onChange={(e) => setSide(e.target.value)}>
              <option value="source">Source (legacy)</option>
              <option value="target">Target (new platform)</option>
            </Select>
          </Field>
        </div>
        {meta && (
          <p className="text-xs text-slate-500">
            Key column <code>{meta.domains[domain].key}</code>; compared fields: {meta.domains[domain].fields.join(", ")}
          </p>
        )}
        {mode === "file" ? (
          <Field label="File">
            <input type="file" accept=".csv,.txt,.psv,.tsv,.parquet,.json" onChange={(e) => setFile(e.target.files?.[0] || null)} className="text-sm" />
          </Field>
        ) : (
          <>
            <Field label="SQLAlchemy URL" hint={meta ? Object.entries(meta.sql_dialects).map(([k, v]) => `${k}: ${v}`).join(" · ") : ""}>
              <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="postgresql+psycopg2://user:pass@host/db" />
            </Field>
            <Field label="Query (SELECT only)">
              <Textarea rows={3} value={query} onChange={(e) => setQuery(e.target.value)} className="font-mono text-xs" />
            </Field>
          </>
        )}
        <ErrorBox error={error} />
        {result && <div className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-700">{result}</div>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button onClick={submit} loading={busy} disabled={mode === "file" ? !file : !url}>
            Load
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function SignOffPanel({ detail, reload }: { detail: RunDetail; reload: () => void }) {
  const { can } = useSession();
  const [area, setArea] = useState<string | null>(null);
  const [decision, setDecision] = useState("APPROVED");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const latest = (a: string) => detail.signoffs.find((s) => s.area === a);
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/api/runs/${detail.run.id}/signoff`, { area, decision, comment });
      setArea(null);
      setComment("");
      reload();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader title="Business sign-off" subtitle={<>Overall: <Badge value={detail.run.signoff_status} /></>} />
      <CardBody className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {AREAS.map((a) => {
          const s = latest(a);
          const blockers = detail.signoff_blockers[a] || 0;
          return (
            <div key={a} className="rounded-md border border-slate-200 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-secondary">{a}</span>
                <Badge value={s?.decision || "PENDING"} />
              </div>
              {s && (
                <div className="mt-1 text-xs text-slate-500">
                  {s.actor} · {fmtDate(s.at)}
                  {s.comment && <div className="italic">“{s.comment}”</div>}
                </div>
              )}
              {blockers > 0 && <div className="mt-1 text-xs text-danger">{blockers} open critical exception(s) block approval</div>}
              {can(`signoff:${a}`) && (
                <Button size="sm" variant="outline" className="mt-2 w-full" onClick={() => setArea(a)}>
                  Record decision
                </Button>
              )}
            </div>
          );
        })}
      </CardBody>
      <Modal open={!!area} onClose={() => setArea(null)} title={`${area} sign-off`}>
        <div className="space-y-3">
          <div className="flex gap-2">
            <Button variant={decision === "APPROVED" ? "success" : "outline"} onClick={() => setDecision("APPROVED")}>
              <CheckCircle2 className="h-4 w-4" /> Approve
            </Button>
            <Button variant={decision === "REJECTED" ? "danger" : "outline"} onClick={() => setDecision("REJECTED")}>
              <XCircle className="h-4 w-4" /> Reject
            </Button>
          </div>
          <Field label="Comment">
            <Textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
          </Field>
          <ErrorBox error={error} />
          <div className="flex justify-end">
            <Button onClick={submit} loading={busy}>
              Submit
            </Button>
          </div>
        </div>
      </Modal>
    </Card>
  );
}

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = Number(params.id);
  const router = useRouter();
  const { can } = useSession();
  const { data, error, loading, reload } = useApi<RunDetail>(`/api/runs/${runId}`);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [loadOpen, setLoadOpen] = useState(false);

  const reconcile = async () => {
    setBusy(true);
    setActionError(null);
    try {
      await api.post(`/api/runs/${runId}/reconcile`, {});
      await reload();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirm("Delete this run and all its reconciliation data?")) return;
    await api.del(`/api/runs/${runId}`);
    router.push("/runs");
  };

  if (loading && !data) return <Spinner />;
  if (!data) return <ErrorBox error={error} />;
  const { run } = data;
  const failedRules = data.rule_results.filter((r) => !r.passed);

  return (
    <>
      <PageHeader
        title={run.name}
        subtitle={`${run.source_system} → ${run.target_system} · ${run.environment} · created by ${run.created_by} ${fmtDate(run.created_at)}`}
        actions={
          <>
            {can("runs:write") && (
              <Button variant="outline" onClick={() => setLoadOpen(true)}>
                <Upload className="h-4 w-4" /> Load data
              </Button>
            )}
            {can("recon:execute") && (
              <Button onClick={reconcile} loading={busy}>
                <Play className="h-4 w-4" /> Run reconciliation
              </Button>
            )}
            <Link href={`/reconciliation?run=${run.id}`}>
              <Button variant="secondary">Open reconciliation</Button>
            </Link>
            {can("runs:write") && (
              <Button variant="ghost" onClick={remove}>
                Delete
              </Button>
            )}
          </>
        }
      />
      <ErrorBox error={actionError} />
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
          <Kpi label="Status" value={<Badge value={run.status} className="text-sm" />} sub={<Progress value={run.progress} tone="bg-primary" />} />
          <Kpi label="Records processed" value={fmtNum(run.records_processed)} tone="secondary" />
          <Kpi label="Reconciliation %" value={fmtPct(run.reconciliation_pct)} tone={run.reconciliation_pct >= 99.9 ? "success" : "warning"} />
          <Kpi label="Failed rules" value={`${failedRules.length}/${data.rule_results.length}`} tone={failedRules.length ? "danger" : "success"} />
        </div>

        <Card>
          <CardHeader title="Domain results" subtitle="Level 2 record matching per domain" />
          <Table>
            <thead>
              <tr>
                <Th>Domain</Th>
                <Th className="text-right">Source</Th>
                <Th className="text-right">Target</Th>
                <Th className="text-right">Matched</Th>
                <Th className="text-right">Mismatched</Th>
                <Th className="text-right">Missing in target</Th>
                <Th className="text-right">Missing in source</Th>
                <Th className="text-right">Match %</Th>
                <Th className="text-right">Open exceptions</Th>
              </tr>
            </thead>
            <tbody>
              {data.domains.map((d) => (
                <tr key={d.domain} className="hover:bg-slate-50">
                  <Td>
                    <Link href={`/reconciliation?run=${run.id}&domain=${d.domain}`} className="font-medium text-primary hover:underline">
                      {DOMAIN_LABEL[d.domain]}
                    </Link>
                  </Td>
                  <Td className="tabular text-right">{fmtNum(d.source_count)}</Td>
                  <Td className="tabular text-right">{fmtNum(d.target_count)}</Td>
                  <Td className="tabular text-right text-success">{fmtNum(d.MATCHED)}</Td>
                  <Td className="tabular text-right">{fmtNum(d.MISMATCHED)}</Td>
                  <Td className="tabular text-right text-danger">{fmtNum(d.MISSING_IN_TARGET)}</Td>
                  <Td className="tabular text-right">{fmtNum(d.MISSING_IN_SOURCE)}</Td>
                  <Td className="tabular text-right font-medium">{d.match_pct === null ? "-" : fmtPct(d.match_pct)}</Td>
                  <Td className="tabular text-right">
                    <Link href={`/exceptions?run_id=${run.id}&domain=${d.domain}`} className="hover:underline">
                      {d.open_exceptions}
                    </Link>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>

        <Card>
          <CardHeader title="Business rule results" subtitle="Reconciliation, threshold, percentage, compliance and completeness rules" />
          <Table>
            <thead>
              <tr>
                <Th>Result</Th>
                <Th>Rule</Th>
                <Th>Category</Th>
                <Th>Domain</Th>
                <Th>Actual</Th>
                <Th>Expected</Th>
                <Th>Detail</Th>
              </tr>
            </thead>
            <tbody>
              {[...data.rule_results].sort((a, b) => Number(a.passed) - Number(b.passed)).map((r) => (
                <tr key={r.rule_id}>
                  <Td>
                    <Badge value={r.passed ? "PASS" : "FAIL"} />
                  </Td>
                  <Td className="font-medium">{r.rule_name}</Td>
                  <Td className="text-xs">{r.category}</Td>
                  <Td className="text-xs uppercase">{r.domain}</Td>
                  <Td className="tabular text-xs">{r.actual}</Td>
                  <Td className="tabular text-xs">{r.expected}</Td>
                  <Td className="text-xs text-slate-500">{r.detail}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>

        <SignOffPanel detail={data} reload={reload} />
      </div>
      {loadOpen && <LoadDataModal runId={runId} open={loadOpen} onClose={() => setLoadOpen(false)} onLoaded={reload} />}
    </>
  );
}
