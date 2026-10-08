"use client";

import { Download } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { BarSeries } from "@/components/charts";
import { RunPicker, useRuns } from "@/components/Scope";
import {
  Badge, Button, Card, CardBody, CardHeader, Empty, ErrorBox, Input, PageHeader, Select, Spinner, Table, Tabs, Td, Th,
} from "@/components/ui";
import { api, qs, RecordItem, Summary } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { cn, DOMAIN_LABEL, DOMAINS, fmtNum } from "@/lib/utils";

type RecordsPage = {
  total: number;
  page: number;
  page_size: number;
  status_counts: Record<string, number>;
  fields: string[];
  key: string;
  items: RecordItem[];
};

type FieldStat = { field: string; mismatches: number; abs_variance: number; compared: number; match_pct: number | null };

const STATUSES = ["", "MISMATCHED", "MISSING_IN_TARGET", "MISSING_IN_SOURCE", "MATCHED"];

function show(v: unknown) {
  if (v === null || v === undefined) return <span className="italic text-slate-400">null</span>;
  if (typeof v === "number") return fmtNum(v, Number.isInteger(v) ? 0 : 2);
  return String(v);
}

function SplitView({ record, fields, keyName }: { record: RecordItem; fields: string[]; keyName: string }) {
  const diffs = new Map(record.field_differences.map((d) => [d.field, d]));
  const allFields = [keyName, ...fields, ...Object.keys(record.source_data || record.target_data || {}).filter((f) => f !== keyName && !fields.includes(f))];
  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <span className="font-semibold text-secondary">{record.record_key}</span>
        <Badge value={record.status} />
        {record.variance > 0 && <span className="tabular text-sm text-danger">Variance {fmtNum(record.variance, 2)}</span>}
      </div>
      <div className="grid grid-cols-[minmax(140px,1fr)_2fr_2fr] overflow-hidden rounded-md border text-sm">
        <div className="bg-slate-50 px-3 py-2 text-[11px] font-semibold uppercase text-slate-500">Field</div>
        <div className="border-l bg-secondary px-3 py-2 text-[11px] font-semibold uppercase text-white">Source (legacy)</div>
        <div className="border-l bg-primary px-3 py-2 text-[11px] font-semibold uppercase text-white">Target (new platform)</div>
        {allFields.map((f) => {
          const d = diffs.get(f);
          const compared = fields.includes(f);
          return (
            <div key={f} className="contents">
              <div className={cn("border-t px-3 py-1.5 font-medium", compared ? "text-slate-700" : "text-slate-400")}>
                {f}
                {d && d.difference !== 0 && typeof d.difference === "number" && (
                  <div className="tabular text-[11px] text-danger">Δ {fmtNum(d.difference, 2)}</div>
                )}
              </div>
              <div className={cn("tabular break-all border-l border-t px-3 py-1.5", d && "bg-red-50")}>{show(record.source_data?.[f])}</div>
              <div className={cn("tabular break-all border-l border-t px-3 py-1.5", d && "bg-red-50 font-medium text-danger")}>
                {show(record.target_data?.[f])}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ReconciliationInner() {
  const router = useRouter();
  const params = useSearchParams();
  const { data: runs } = useRuns();
  const runParam = params.get("run");
  const runId = runParam ? Number(runParam) : runs?.[0]?.id ?? "";
  const domain = params.get("domain") || "balance";
  const selectedKey = params.get("key");
  const [level, setLevel] = useState<"L1" | "L2" | "L3">(selectedKey ? "L2" : "L2");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState(selectedKey || "");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<RecordItem | null>(null);

  const setParam = (k: string, v: string | number) => {
    const p = new URLSearchParams(params.toString());
    p.set(k, String(v));
    if (k !== "key") p.delete("key");
    router.replace(`/reconciliation?${p.toString()}`);
    setPage(1);
    setSelected(null);
  };

  useEffect(() => setPage(1), [status, search]);

  const summary = useApi<Summary[]>(runId ? `/api/recon/${runId}/summary${qs({ domain })}` : null);
  const records = useApi<RecordsPage>(runId ? `/api/recon/${runId}/records${qs({ domain, status, search, page, page_size: 25 })}` : null);
  const fields = useApi<FieldStat[]>(runId ? `/api/recon/${runId}/fields/${domain}` : null);

  useEffect(() => {
    if (selectedKey && records.data && !selected) {
      const r = records.data.items.find((i) => i.record_key === selectedKey);
      if (r) setSelected(r);
    }
  }, [selectedKey, records.data, selected]);

  const fieldChart = useMemo(() => (fields.data || []).map((f) => ({ name: f.field, mismatches: f.mismatches })), [fields.data]);

  return (
    <>
      <PageHeader
        title="Reconciliation"
        subtitle="Level 1 totals · Level 2 record matching · Level 3 field comparison with split-view drill-down"
        actions={<RunPicker value={runId} onChange={(v) => setParam("run", v)} allowAll={false} />}
      />
      <div className="mb-4 flex flex-wrap gap-1.5">
        {DOMAINS.map((d) => (
          <button
            key={d}
            onClick={() => setParam("domain", d)}
            className={cn(
              "rounded-full border px-3 py-1 text-sm transition",
              d === domain ? "border-primary bg-primary text-white" : "border-slate-200 bg-white text-slate-600 hover:border-primary",
            )}
          >
            {DOMAIN_LABEL[d]}
          </button>
        ))}
      </div>
      {!runId ? (
        <Empty>Select a run.</Empty>
      ) : (
        <Card>
          <div className="px-4 pt-2">
            <Tabs
              value={level}
              onChange={setLevel}
              tabs={[
                { value: "L1", label: "Level 1 · Totals" },
                { value: "L2", label: `Level 2 · Records${records.data ? ` (${fmtNum(records.data.total)})` : ""}` },
                { value: "L3", label: "Level 3 · Fields" },
              ]}
            />
          </div>
          {level === "L1" && (
            <CardBody>
              <ErrorBox error={summary.error} />
              {summary.loading && !summary.data ? (
                <Spinner />
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <Th>Metric</Th>
                      <Th className="text-right">Source</Th>
                      <Th className="text-right">Target</Th>
                      <Th className="text-right">Difference</Th>
                      <Th>Result</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {(summary.data || []).map((s) => (
                      <tr key={s.metric}>
                        <Td className="font-medium">{s.metric.replace(/_/g, " ")}</Td>
                        <Td className="tabular text-right">{fmtNum(s.source_value, 2)}</Td>
                        <Td className="tabular text-right">{fmtNum(s.target_value, 2)}</Td>
                        <Td className={cn("tabular text-right", s.difference !== 0 && "font-medium text-danger")}>{fmtNum(s.difference, 2)}</Td>
                        <Td>
                          <Badge value={s.matched ? "MATCHED" : "MISMATCHED"} />
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </CardBody>
          )}
          {level === "L2" && (
            <div className="grid min-h-[520px] lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
              <div className="border-r">
                <div className="flex flex-wrap items-center gap-2 border-b p-3">
                  <Input className="w-48" placeholder={`Search ${records.data?.key || "key"}`} value={search} onChange={(e) => setSearch(e.target.value)} />
                  <Select value={status} onChange={(e) => setStatus(e.target.value)}>
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s ? `${s.replace(/_/g, " ")} (${records.data?.status_counts[s] ?? 0})` : "All statuses"}
                      </option>
                    ))}
                  </Select>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => api.download(`/api/recon/${runId}/records/export${qs({ domain, status, search })}`, `${domain}_records.csv`)}
                  >
                    <Download className="h-3.5 w-3.5" /> CSV
                  </Button>
                </div>
                <ErrorBox error={records.error} />
                {records.loading && !records.data ? (
                  <Spinner />
                ) : !records.data?.items.length ? (
                  <Empty>No records.</Empty>
                ) : (
                  <>
                    <Table>
                      <thead>
                        <tr>
                          <Th>{records.data.key}</Th>
                          <Th>Status</Th>
                          <Th>Differences</Th>
                          <Th className="text-right">Variance</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {records.data.items.map((r) => (
                          <tr
                            key={r.id}
                            onClick={() => setSelected(r)}
                            className={cn("cursor-pointer hover:bg-slate-50", selected?.id === r.id && "bg-primary-50")}
                          >
                            <Td className="font-medium text-secondary">{r.record_key}</Td>
                            <Td>
                              <Badge value={r.status} />
                            </Td>
                            <Td className="text-xs text-slate-600">{r.field_differences.map((d) => d.field).join(", ") || "-"}</Td>
                            <Td className="tabular text-right">{r.variance ? fmtNum(r.variance, 2) : "-"}</Td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                    <div className="flex items-center justify-between p-3 text-xs text-slate-500">
                      <span>
                        Page {records.data.page} of {Math.max(1, Math.ceil(records.data.total / records.data.page_size))}
                      </span>
                      <div className="flex gap-1">
                        <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                          Prev
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={page * records.data.page_size >= records.data.total}
                          onClick={() => setPage(page + 1)}
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  </>
                )}
              </div>
              <div className="p-4">
                {selected && records.data ? (
                  <SplitView record={selected} fields={records.data.fields} keyName={records.data.key} />
                ) : (
                  <Empty>Select a record to compare source and target side by side.</Empty>
                )}
              </div>
            </div>
          )}
          {level === "L3" && (
            <CardBody className="grid gap-4 lg:grid-cols-2">
              <div>
                <CardHeader title="Mismatches by field" className="border-0 px-0 pt-0" />
                <BarSeries data={fieldChart} series={[{ key: "mismatches", label: "Mismatches", color: "#DC3545" }]} layout="vertical" height={300} />
              </div>
              <Table>
                <thead>
                  <tr>
                    <Th>Field</Th>
                    <Th className="text-right">Compared</Th>
                    <Th className="text-right">Mismatches</Th>
                    <Th className="text-right">Match %</Th>
                    <Th className="text-right">Abs. variance</Th>
                  </tr>
                </thead>
                <tbody>
                  {(fields.data || []).map((f) => (
                    <tr key={f.field}>
                      <Td className="font-medium">{f.field}</Td>
                      <Td className="tabular text-right">{fmtNum(f.compared)}</Td>
                      <Td className={cn("tabular text-right", f.mismatches > 0 && "font-medium text-danger")}>{fmtNum(f.mismatches)}</Td>
                      <Td className="tabular text-right">{f.match_pct === null ? "-" : `${f.match_pct.toFixed(2)}%`}</Td>
                      <Td className="tabular text-right">{f.abs_variance ? fmtNum(f.abs_variance, 2) : "-"}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </CardBody>
          )}
        </Card>
      )}
    </>
  );
}

export default function ReconciliationPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <ReconciliationInner />
    </Suspense>
  );
}
