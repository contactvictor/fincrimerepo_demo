"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useRuns } from "@/components/Scope";
import {
  Badge, Button, Card, Empty, ErrorBox, Field, Input, Modal, PageHeader, Progress, Select, Spinner, Table, Td, Textarea, Th,
} from "@/components/ui";
import { api, Meta, Run } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtDate, fmtNum, fmtPct } from "@/lib/utils";

function NewRunModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const { data: meta } = useApi<Meta>("/api/meta");
  const [form, setForm] = useState({
    name: "",
    description: "",
    source_system: "Oracle",
    target_system: "Actimize",
    environment: "UAT",
    generate_demo_data: true,
    demo_customers: 200,
    defect_level: 0.5,
  });
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const run = await api.post<Run>("/api/runs", form);
      router.push(`/runs/${run.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="New migration run">
      <div className="space-y-3">
        <Field label="Name">
          <Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Wave 4 - Wealth Management" />
        </Field>
        <Field label="Description">
          <Textarea rows={2} value={form.description} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Source system">
            <Select className="w-full" value={form.source_system} onChange={(e) => set("source_system", e.target.value)}>
              {meta?.source_systems.map((s) => <option key={s}>{s}</option>)}
            </Select>
          </Field>
          <Field label="Target system">
            <Select className="w-full" value={form.target_system} onChange={(e) => set("target_system", e.target.value)}>
              {meta?.target_systems.map((s) => <option key={s}>{s}</option>)}
            </Select>
          </Field>
          <Field label="Environment">
            <Select className="w-full" value={form.environment} onChange={(e) => set("environment", e.target.value)}>
              {meta?.environments.map((s) => <option key={s}>{s}</option>)}
            </Select>
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.generate_demo_data} onChange={(e) => set("generate_demo_data", e.target.checked)} />
          Generate synthetic source/target data (otherwise upload files or extract via SQL)
        </label>
        {form.generate_demo_data && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Customers">
              <Input type="number" min={10} max={20000} value={form.demo_customers} onChange={(e) => set("demo_customers", Number(e.target.value))} />
            </Field>
            <Field label="Defect level (0 = clean, 5 = very dirty)">
              <Input type="number" step={0.1} min={0} max={5} value={form.defect_level} onChange={(e) => set("defect_level", Number(e.target.value))} />
            </Field>
          </div>
        )}
        <ErrorBox error={error} />
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} loading={saving} disabled={form.name.length < 3}>
            Create run
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default function RunsPage() {
  const { can } = useSession();
  const { data, error, loading } = useRuns();
  const [open, setOpen] = useState(false);

  return (
    <>
      <PageHeader
        title="Migration Runs"
        subtitle="Each run reconciles one migration wave between a source and a target platform"
        actions={
          can("runs:write") && (
            <Button onClick={() => setOpen(true)}>
              <Plus className="h-4 w-4" /> New run
            </Button>
          )
        }
      />
      <ErrorBox error={error} />
      <Card>
        {loading && !data ? (
          <Spinner />
        ) : !data?.length ? (
          <Empty>No migration runs in this environment.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>#</Th>
                <Th>Name</Th>
                <Th>Source → Target</Th>
                <Th>Env</Th>
                <Th>Status</Th>
                <Th className="w-36">Progress</Th>
                <Th className="text-right">Records</Th>
                <Th className="text-right">Recon %</Th>
                <Th>Sign-off</Th>
                <Th>Completed</Th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <Td className="text-slate-500">{r.id}</Td>
                  <Td>
                    <Link href={`/runs/${r.id}`} className="font-medium text-primary hover:underline">
                      {r.name}
                    </Link>
                    <div className="text-xs text-slate-500">{r.description}</div>
                  </Td>
                  <Td className="text-xs">
                    {r.source_system} → {r.target_system}
                  </Td>
                  <Td>{r.environment}</Td>
                  <Td>
                    <Badge value={r.status} />
                  </Td>
                  <Td>
                    <Progress value={r.progress} tone="bg-primary" />
                  </Td>
                  <Td className="tabular text-right">{fmtNum(r.records_processed)}</Td>
                  <Td className="tabular text-right">{fmtPct(r.reconciliation_pct)}</Td>
                  <Td>
                    <Badge value={r.signoff_status} />
                  </Td>
                  <Td className="text-xs text-slate-500">{fmtDate(r.completed_at)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {open && <NewRunModal open={open} onClose={() => setOpen(false)} />}
    </>
  );
}
