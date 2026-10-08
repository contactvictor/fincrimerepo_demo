"use client";

import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { Empty } from "@/components/ui";
import { COLORS, cn, fmtCompact, fmtNum } from "@/lib/utils";

type Datum = Record<string, string | number | null | undefined>;

const tick = { fontSize: 11, fill: "#64748b" };

export function BarSeries({ data, x = "name", series, height = 240, layout = "horizontal", stacked }: {
  data: Datum[];
  x?: string;
  series: { key: string; label: string; color?: string }[];
  height?: number;
  layout?: "horizontal" | "vertical";
  stacked?: boolean;
}) {
  if (!data.length) return <Empty>No data</Empty>;
  const vertical = layout === "vertical";
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={layout} margin={{ left: vertical ? 40 : 0, right: 12, top: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        {vertical ? (
          <>
            <XAxis type="number" tick={tick} tickFormatter={(v) => fmtCompact(v)} />
            <YAxis type="category" dataKey={x} tick={tick} width={110} />
          </>
        ) : (
          <>
            <XAxis
              dataKey={x}
              tick={tick}
              interval={0}
              angle={data.length > 6 ? -35 : 0}
              textAnchor={data.length > 6 ? "end" : "middle"}
              height={data.length > 6 ? 55 : 30}
            />
            <YAxis tick={tick} tickFormatter={(v) => fmtCompact(v)} width={60} />
          </>
        )}
        <Tooltip formatter={(v: number) => fmtNum(v, 2)} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.label}
            fill={s.color || COLORS.palette[i]}
            radius={stacked ? 0 : 3}
            stackId={stacked ? "a" : undefined}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Donut({ data, height = 220, colors }: { data: { name: string; count: number }[]; height?: number; colors?: Record<string, string> }) {
  if (!data.length) return <Empty>No data</Empty>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={data} dataKey="count" nameKey="name" innerRadius="55%" outerRadius="85%" paddingAngle={2}>
          {data.map((d, i) => (
            <Cell key={d.name} fill={colors?.[d.name] || COLORS.palette[i % COLORS.palette.length]} />
          ))}
        </Pie>
        <Tooltip formatter={(v: number) => fmtNum(v)} />
        <Legend wrapperStyle={{ fontSize: 11 }} layout="vertical" align="right" verticalAlign="middle" />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function Trend({ data, height = 220 }: { data: { date: string; detected: number; resolved: number }[]; height?: number }) {
  if (!data.length) return <Empty>No data</Empty>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ right: 12, top: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="date" tick={tick} tickFormatter={(d: string) => d.slice(5)} />
        <YAxis tick={tick} width={40} allowDecimals={false} />
        <Tooltip />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="detected" name="Detected" stroke={COLORS.danger} strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="resolved" name="Resolved" stroke={COLORS.success} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function heatColor(v: number | null) {
  if (v === null) return "bg-slate-100 text-slate-400";
  if (v >= 99.9) return "bg-green-100 text-green-800";
  if (v >= 99) return "bg-lime-100 text-lime-800";
  if (v >= 95) return "bg-amber-100 text-amber-800";
  return "bg-red-100 text-red-800";
}

export function Heatmap({ rows }: { rows: { domain: string; L1: number | null; L2: number | null; L3: number | null }[] }) {
  const levels = [
    ["L1", "Level 1 · Totals"],
    ["L2", "Level 2 · Records"],
    ["L3", "Level 3 · Fields"],
  ] as const;
  return (
    <table className="w-full text-sm">
      <thead>
        <tr>
          <th className="px-2 py-1 text-left text-[11px] font-semibold uppercase text-slate-500">Domain</th>
          {levels.map(([, l]) => (
            <th key={l} className="px-2 py-1 text-center text-[11px] font-semibold uppercase text-slate-500">
              {l}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.domain}>
            <td className="px-2 py-1 font-medium capitalize text-secondary">{r.domain}</td>
            {levels.map(([k]) => (
              <td key={k} className="p-0.5">
                <div className={cn("tabular rounded px-2 py-1.5 text-center text-xs font-semibold", heatColor(r[k]))}>
                  {r[k] === null ? "n/a" : `${r[k]!.toFixed(2)}%`}
                </div>
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: COLORS.danger,
  HIGH: "#F97316",
  MEDIUM: COLORS.warning,
  LOW: "#94A3B8",
};

export const STATUS_COLORS: Record<string, string> = {
  DETECTED: COLORS.danger,
  ASSIGNED: COLORS.primary,
  INVESTIGATING: COLORS.warning,
  RESOLVED: COLORS.success,
  CLOSED: "#94A3B8",
};
