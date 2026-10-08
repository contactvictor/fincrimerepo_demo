"use client";

import { Plus } from "lucide-react";
import { useState } from "react";

import {
  Badge, Button, Card, Empty, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, Table, Tabs, Td, Textarea, Th,
} from "@/components/ui";
import { api, Me, Rule } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { DOMAIN_LABEL, DOMAINS, fmtDate, label } from "@/lib/utils";

type AuditLog = { id: number; actor: string; action: string; entity: string; entity_id: string; detail: Record<string, unknown>; at: string };

const RULE_CATEGORIES = ["RECONCILIATION", "THRESHOLD", "PERCENTAGE_THRESHOLD", "COMPLIANCE", "COMPLETENESS"];
const PARAM_EXAMPLES: Record<string, string> = {
  RECONCILIATION: '{"metric": "record_count", "tolerance": 0}',
  THRESHOLD: '{"field": "current_balance", "measure": "total_abs_variance", "operator": "<=", "value": 1000}',
  PERCENTAGE_THRESHOLD: '{"max_mismatch_pct": 0.01}',
  COMPLIANCE: '{"filter_field": "risk_rating", "filter_values": ["HIGH"], "required_fields": ["risk_rating", "risk_score"]}',
  COMPLETENESS: '{"mandatory_fields": ["customer_id", "full_name"]}',
};
const ROLES = ["admin", "analyst", "finance", "compliance", "auditor"];

function RuleModal({ rule, onClose, onSaved }: { rule: Partial<Rule> | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    name: rule?.name || "",
    description: rule?.description || "",
    category: rule?.category || "THRESHOLD",
    domain: rule?.domain || "balance",
    severity: rule?.severity || "HIGH",
    active: rule?.active ?? true,
    params: rule?.params ? JSON.stringify(rule.params, null, 2) : PARAM_EXAMPLES.THRESHOLD,
  });
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const body = { ...form, params: JSON.parse(form.params) };
      if (rule?.id) await api.put(`/api/rules/${rule.id}`, body);
      else await api.post("/api/rules", body);
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof SyntaxError ? new Error(`Parameters must be valid JSON: ${e.message}`) : e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open onClose={onClose} title={rule?.id ? "Edit rule" : "New business rule"}>
      <div className="space-y-3">
        <Field label="Name">
          <Input value={form.name} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label="Description">
          <Input value={form.description} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Category">
            <Select
              className="w-full"
              value={form.category}
              onChange={(e) => {
                set("category", e.target.value);
                if (!rule?.id) set("params", PARAM_EXAMPLES[e.target.value]);
              }}
            >
              {RULE_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {label(c)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Domain">
            <Select className="w-full" value={form.domain} onChange={(e) => set("domain", e.target.value)}>
              {DOMAINS.map((d) => (
                <option key={d} value={d}>
                  {DOMAIN_LABEL[d]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Severity">
            <Select className="w-full" value={form.severity} onChange={(e) => set("severity", e.target.value)}>
              {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Parameters (JSON)" hint={`Example: ${PARAM_EXAMPLES[form.category]}`}>
          <Textarea rows={5} className="font-mono text-xs" value={form.params} onChange={(e) => set("params", e.target.value)} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.active} onChange={(e) => set("active", e.target.checked)} /> Active
        </label>
        <ErrorBox error={error} />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save} loading={saving}>
            Save
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function RulesTab() {
  const { can } = useSession();
  const { data, error, loading, reload } = useApi<Rule[]>("/api/rules");
  const [editing, setEditing] = useState<Partial<Rule> | null>(null);
  const remove = async (id: number) => {
    if (!confirm("Delete this rule?")) return;
    await api.del(`/api/rules/${id}`);
    reload();
  };
  return (
    <>
      {can("rules:write") && (
        <div className="flex justify-end p-3">
          <Button size="sm" onClick={() => setEditing({})}>
            <Plus className="h-4 w-4" /> New rule
          </Button>
        </div>
      )}
      <ErrorBox error={error} />
      {loading && !data ? (
        <Spinner />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Rule</Th>
              <Th>Category</Th>
              <Th>Domain</Th>
              <Th>Parameters</Th>
              <Th>Severity</Th>
              <Th>Active</Th>
              {can("rules:write") && <Th />}
            </tr>
          </thead>
          <tbody>
            {(data || []).map((r) => (
              <tr key={r.id}>
                <Td>
                  <div className="font-medium">{r.name}</div>
                  <div className="text-xs text-slate-500">{r.description}</div>
                </Td>
                <Td className="text-xs">{label(r.category)}</Td>
                <Td className="text-xs uppercase">{r.domain}</Td>
                <Td className="font-mono text-[11px] text-slate-600">{JSON.stringify(r.params)}</Td>
                <Td>
                  <Badge value={r.severity} />
                </Td>
                <Td>{r.active ? <Badge value="PASS">Active</Badge> : <Badge value="CLOSED">Inactive</Badge>}</Td>
                {can("rules:write") && (
                  <Td className="whitespace-nowrap">
                    <Button size="sm" variant="ghost" onClick={() => setEditing(r)}>
                      Edit
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => remove(r.id)}>
                      Delete
                    </Button>
                  </Td>
                )}
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {editing && <RuleModal rule={editing} onClose={() => setEditing(null)} onSaved={reload} />}
    </>
  );
}

function UsersTab() {
  const { data, error, loading, reload } = useApi<Me[]>("/api/admin/users");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ username: "", full_name: "", email: "", role: "analyst", password: "" });
  const [formError, setFormError] = useState<unknown>(null);

  const create = async () => {
    setFormError(null);
    try {
      await api.post("/api/admin/users", form);
      setOpen(false);
      setForm({ username: "", full_name: "", email: "", role: "analyst", password: "" });
      reload();
    } catch (e) {
      setFormError(e);
    }
  };
  const update = async (u: Me, patch: Partial<Me>) => {
    await api.put(`/api/admin/users/${u.id}`, patch);
    reload();
  };

  return (
    <>
      <div className="flex justify-end p-3">
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> New user
        </Button>
      </div>
      <ErrorBox error={error} />
      {loading && !data ? (
        <Spinner />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Username</Th>
              <Th>Name</Th>
              <Th>Email</Th>
              <Th>Role</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {(data || []).map((u) => (
              <tr key={u.id}>
                <Td className="font-medium">{u.username}</Td>
                <Td>{u.full_name}</Td>
                <Td className="text-xs">{u.email}</Td>
                <Td>
                  <Select value={u.role} onChange={(e) => update(u, { role: e.target.value })} className="h-8 text-xs">
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {label(r)}
                      </option>
                    ))}
                  </Select>
                </Td>
                <Td>
                  <Button size="sm" variant={u.active ? "outline" : "success"} onClick={() => update(u, { active: !u.active })}>
                    {u.active ? "Deactivate" : "Activate"}
                  </Button>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="New user">
        <div className="space-y-3">
          {(["username", "full_name", "email", "password"] as const).map((k) => (
            <Field key={k} label={label(k)}>
              <Input type={k === "password" ? "password" : "text"} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
            </Field>
          ))}
          <Field label="Role">
            <Select className="w-full" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {label(r)}
                </option>
              ))}
            </Select>
          </Field>
          <ErrorBox error={formError} />
          <div className="flex justify-end">
            <Button onClick={create}>Create</Button>
          </div>
        </div>
      </Modal>
    </>
  );
}

function AuditTab() {
  const { data, error, loading } = useApi<AuditLog[]>("/api/admin/audit-logs");
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  if (!data?.length) return <Empty>No audit entries.</Empty>;
  return (
    <Table>
      <thead>
        <tr>
          <Th>When</Th>
          <Th>Actor</Th>
          <Th>Action</Th>
          <Th>Entity</Th>
          <Th>Detail</Th>
        </tr>
      </thead>
      <tbody>
        {data.map((l) => (
          <tr key={l.id}>
            <Td className="whitespace-nowrap text-xs text-slate-500">{fmtDate(l.at)}</Td>
            <Td className="font-medium">{l.actor}</Td>
            <Td>
              <Badge>{l.action}</Badge>
            </Td>
            <Td className="text-xs">
              {l.entity} {l.entity_id && `#${l.entity_id}`}
            </Td>
            <Td className="max-w-xl truncate font-mono text-[11px] text-slate-500">{JSON.stringify(l.detail)}</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export default function AdminPage() {
  const { can } = useSession();
  const tabs = [
    { value: "rules" as const, label: "Business rules" },
    ...(can("admin") ? [{ value: "users" as const, label: "Users & roles" }] : []),
    ...(can("audit:read") ? [{ value: "audit" as const, label: "Audit log" }] : []),
  ];
  const [tab, setTab] = useState<"rules" | "users" | "audit">("rules");
  return (
    <>
      <PageHeader title="Administration" subtitle="Business rules, user access and the immutable audit trail" />
      <Card>
        <div className="px-4 pt-2">
          <Tabs value={tab} onChange={setTab} tabs={tabs} />
        </div>
        {tab === "rules" && <RulesTab />}
        {tab === "users" && <UsersTab />}
        {tab === "audit" && <AuditTab />}
      </Card>
    </>
  );
}
