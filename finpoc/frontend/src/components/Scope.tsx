"use client";

import { Select } from "@/components/ui";
import { Run } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { qs } from "@/lib/api";

export function useRuns() {
  const { environment } = useSession();
  return useApi<Run[]>(`/api/runs${qs({ environment })}`);
}

export function RunPicker({ value, onChange, allowAll = true }: {
  value: number | "";
  onChange: (v: number | "") => void;
  allowAll?: boolean;
}) {
  const { data } = useRuns();
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")} className="min-w-64">
      {allowAll && <option value="">All runs in scope</option>}
      {!allowAll && !value && <option value="">Select a run</option>}
      {(data || []).map((r) => (
        <option key={r.id} value={r.id}>
          #{r.id} · {r.name} ({r.environment})
        </option>
      ))}
    </Select>
  );
}

export function scopeQuery(environment: string, runId: number | "") {
  return qs({ environment, run_id: runId || undefined });
}
