"use client";

import { Bot, Download } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { RunPicker } from "@/components/Scope";
import {
  Badge, Button, Card, Drawer, Empty, ErrorBox, Field, Input, PageHeader, Select, Spinner, Table, Td, Textarea, Th,
} from "@/components/ui";
import { api, ExceptionDetail, ExceptionItem, qs } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { DOMAIN_LABEL, DOMAINS, fmtDate, fmtNum, label } from "@/lib/utils";

type ExceptionPage = { total: number; page: number; page_size: number; items: ExceptionItem[] };
type Explain = { code: string; root_cause: string; explanation: string; recommended_action: string; similar: number; provider: string };

const CATEGORIES = ["MISSING_RECORD", "UNEXPECTED_RECORD", "DUPLICATE_RECORD", "BALANCE_VARIANCE", "MAPPING_ISSUE", "AML_VALIDATION_FAILURE", "RULE_FAILURE"];
const SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
const STATUSES = ["DETECTED", "ASSIGNED", "INVESTIGATING", "RESOLVED", "CLOSED"];
const ROOT_CAUSES = ["SOURCE_ISSUE", "TRANSFORMATION_ISSUE", "LOAD_ISSUE", "MAPPING_ISSUE", "MISSING_RECORDS", "DATA_QUALITY_ISSUE"];
const ACTION_LABEL: Record<string, string> = {
  ASSIGNED: "Assign",
  INVESTIGATING: "Start investigation",
  RESOLVED: "Resolve",
  CLOSED: "Close",
};

function ExceptionDrawer({ code, onClose, onChanged }: { code: string; onClose: () => void; onChanged: () => void }) {
  const { can, canDomain, user } = useSession();
  const { data, error, loading, setData } = useApi<ExceptionDetail>(`/api/exceptions/${code}`);
  const [explain, setExplain] = useState<Explain | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [owner, setOwner] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  useEffect(() => {
    setOwner(data?.owner || user?.username || "");
  }, [data?.owner, user?.username]);

  const move = async (to_status: string) => {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api.post<ExceptionDetail>(`/api/exceptions/${code}/transition`, { to_status, owner, comment });
      setData(updated);
      setComment("");
      onChanged();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };

  const runExplain = async () => {
    setExplaining(true);
    try {
      setExplain(await api.get<Explain>(`/api/exceptions/${code}/explain`));
    } finally {
      setExplaining(false);
    }
  };

  return (
    <Drawer open onClose={onClose} title={code}>
      {loading && !data && <Spinner />}
      <ErrorBox error={error} />
      {data && (
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap gap-1.5">
            <Badge value={data.severity} />
            <Badge value={data.status} />
            <Badge>{label(data.category)}</Badge>
            <Badge>{DOMAIN_LABEL[data.domain]}</Badge>
          </div>
          <p className="text-slate-700">{data.description}</p>
          <dl className="grid grid-cols-[120px_1fr] gap-x-3 gap-y-1.5">
            <dt className="text-slate-500">Run</dt>
            <dd>#{data.run_id}</dd>
            <dt className="text-slate-500">Record</dt>
            <dd>
              {data.record_key ? (
                <a className="text-primary hover:underline" href={`/reconciliation?run=${data.run_id}&domain=${data.domain}&key=${data.record_key}`}>
                  {data.record_key}
                </a>
              ) : (
                "-"
              )}
            </dd>
            <dt className="text-slate-500">Field</dt>
            <dd>{data.field || "-"}</dd>
            <dt className="text-slate-500">Source value</dt>
            <dd className="tabular break-all">{data.source_value ?? <i className="text-slate-400">null</i>}</dd>
            <dt className="text-slate-500">Target value</dt>
            <dd className="tabular break-all text-danger">{data.target_value ?? <i className="text-slate-400">null</i>}</dd>
            <dt className="text-slate-500">Variance</dt>
            <dd className="tabular">{data.variance ? fmtNum(data.variance, 2) : "-"}</dd>
            <dt className="text-slate-500">Root cause</dt>
            <dd>
              <span className="font-medium">{label(data.root_cause)}</span>
              <div className="text-xs text-slate-500">{data.root_cause_detail}</div>
            </dd>
            <dt className="text-slate-500">Owner</dt>
            <dd>{data.owner || "-"}</dd>
            {data.resolution && (
              <>
                <dt className="text-slate-500">Resolution</dt>
                <dd>{data.resolution}</dd>
              </>
            )}
          </dl>

          <div className="rounded-md border border-primary-100 bg-primary-50 p-3">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 font-medium text-secondary">
                <Bot className="h-4 w-4" /> AI root-cause analysis
              </span>
              <Button size="sm" variant="outline" onClick={runExplain} loading={explaining}>
                Explain
              </Button>
            </div>
            {explain && (
              <div className="mt-2 space-y-1.5 text-slate-700">
                <p>{explain.explanation}</p>
                {explain.recommended_action && !explain.explanation.includes(explain.recommended_action) && (
                  <p>
                    <span className="font-medium">Recommended action:</span> {explain.recommended_action}
                  </p>
                )}
                <p className="text-xs text-slate-500">
                  {explain.similar} similar exception(s) in this run · provider: {explain.provider}
                </p>
              </div>
            )}
          </div>

          {can("exceptions:update") && !canDomain(data.domain) && data.allowed_transitions.length > 0 && (
            <p className="rounded-md border bg-slate-50 p-3 text-xs text-slate-500">
              Your role cannot act on {label(data.domain)} exceptions.
            </p>
          )}
          {can("exceptions:update") && canDomain(data.domain) && data.allowed_transitions.length > 0 && (
            <div className="space-y-2 rounded-md border p-3">
              <div className="font-medium text-secondary">Workflow</div>
              {data.allowed_transitions.includes("ASSIGNED") && (
                <Field label="Owner">
                  <Input value={owner} onChange={(e) => setOwner(e.target.value)} />
                </Field>
              )}
              <Field label="Comment" hint="A resolution comment is required to resolve. Closing requires a different user than the owner (four-eyes).">
                <Textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
              </Field>
              <ErrorBox error={actionError} />
              <div className="flex flex-wrap gap-2">
                {data.allowed_transitions.map((t) => (
                  <Button key={t} size="sm" variant={t === "CLOSED" ? "success" : "primary"} loading={busy} onClick={() => move(t)}>
                    {t === data.status ? "Reassign" : ACTION_LABEL[t] || t}
                  </Button>
                ))}
              </div>
            </div>
          )}

          <div>
            <div className="mb-2 font-medium text-secondary">History</div>
            {data.history.length === 0 ? (
              <div className="text-xs text-slate-500">No workflow activity yet.</div>
            ) : (
              <ol className="space-y-2 border-l-2 border-primary-100 pl-3">
                {data.history.map((h, i) => (
                  <li key={i}>
                    <div className="flex items-center gap-1.5 text-xs">
                      {h.from_status && <Badge value={h.from_status} />} → <Badge value={h.to_status} />
                      <span className="text-slate-500">
                        {h.actor} · {fmtDate(h.at)}
                      </span>
                    </div>
                    {h.comment && <div className="mt-0.5 text-xs text-slate-600">{h.comment}</div>}
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      )}
    </Drawer>
  );
}

function ExceptionsInner() {
  const params = useSearchParams();
  const [filters, setFilters] = useState({
    run_id: params.get("run_id") ? Number(params.get("run_id")) : ("" as number | ""),
    domain: params.get("domain") || "",
    category: "",
    severity: "",
    status: "",
    root_cause: "",
    search: "",
  });
  const [page, setPage] = useState(1);
  const [code, setCode] = useState<string | null>(params.get("code"));
  const set = (k: string, v: unknown) => {
    setFilters((f) => ({ ...f, [k]: v }));
    setPage(1);
  };
  const query = qs({ ...filters, page, page_size: 25 });
  const { data, error, loading, reload } = useApi<ExceptionPage>(`/api/exceptions${query}`);

  return (
    <>
      <PageHeader
        title="Exception Management"
        subtitle="Detected → Assigned → Investigating → Resolved → Closed"
        actions={
          <Button variant="outline" onClick={() => api.download(`/api/exceptions/export${qs(filters)}`, "exceptions.csv")}>
            <Download className="h-4 w-4" /> Export CSV
          </Button>
        }
      />
      <Card className="mb-4 flex flex-wrap items-center gap-2 p-3">
        <RunPicker value={filters.run_id} onChange={(v) => set("run_id", v)} />
        <Select value={filters.domain} onChange={(e) => set("domain", e.target.value)}>
          <option value="">All domains</option>
          {DOMAINS.map((d) => (
            <option key={d} value={d}>
              {DOMAIN_LABEL[d]}
            </option>
          ))}
        </Select>
        {(
          [
            ["category", CATEGORIES, "All categories"],
            ["severity", SEVERITIES, "All severities"],
            ["status", STATUSES, "All statuses"],
            ["root_cause", ROOT_CAUSES, "All root causes"],
          ] as const
        ).map(([k, opts, all]) => (
          <Select key={k} value={filters[k]} onChange={(e) => set(k, e.target.value)}>
            <option value="">{all}</option>
            {opts.map((o) => (
              <option key={o} value={o}>
                {label(o)}
              </option>
            ))}
          </Select>
        ))}
        <Input className="w-56" placeholder="Search code, record, description" value={filters.search} onChange={(e) => set("search", e.target.value)} />
      </Card>
      <ErrorBox error={error} />
      <Card>
        {loading && !data ? (
          <Spinner />
        ) : !data?.items.length ? (
          <Empty>No exceptions match the filters.</Empty>
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Code</Th>
                  <Th>Severity</Th>
                  <Th>Domain</Th>
                  <Th>Category</Th>
                  <Th>Record</Th>
                  <Th>Description</Th>
                  <Th>Root cause</Th>
                  <Th>Owner</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((e) => (
                  <tr key={e.id} onClick={() => setCode(e.code)} className="cursor-pointer hover:bg-slate-50">
                    <Td className="font-medium text-primary">{e.code}</Td>
                    <Td>
                      <Badge value={e.severity} />
                    </Td>
                    <Td className="text-xs uppercase">{e.domain}</Td>
                    <Td className="text-xs">{label(e.category)}</Td>
                    <Td className="text-xs">{e.record_key || "-"}</Td>
                    <Td className="max-w-md text-xs text-slate-600">{e.description}</Td>
                    <Td className="text-xs">{label(e.root_cause)}</Td>
                    <Td className="text-xs">{e.owner || "-"}</Td>
                    <Td>
                      <Badge value={e.status} />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <div className="flex items-center justify-between p-3 text-xs text-slate-500">
              <span>
                {fmtNum(data.total)} exceptions · page {data.page} of {Math.max(1, Math.ceil(data.total / data.page_size))}
              </span>
              <div className="flex gap-1">
                <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  Prev
                </Button>
                <Button size="sm" variant="outline" disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>
      {code && <ExceptionDrawer key={code} code={code} onClose={() => setCode(null)} onChanged={reload} />}
    </>
  );
}

export default function ExceptionsPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <ExceptionsInner />
    </Suspense>
  );
}
