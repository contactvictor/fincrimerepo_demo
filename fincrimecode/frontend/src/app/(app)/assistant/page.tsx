"use client";

import { Bot, Send, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { RunPicker } from "@/components/Scope";
import { Badge, Button, Card, Input, PageHeader, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtNum, label } from "@/lib/utils";

type Answer = {
  question: string;
  intent: string;
  provider: string;
  answer: string;
  table: Record<string, unknown>[];
};

type Message = { role: "user"; text: string } | { role: "assistant"; answer: Answer } | { role: "error"; text: string };

function Cell({ v }: { v: unknown }) {
  if (typeof v === "number") return <>{fmtNum(v, Number.isInteger(v) ? 0 : 2)}</>;
  if (v === null || v === undefined) return <>-</>;
  if (typeof v === "object") return <>{JSON.stringify(v)}</>;
  return <>{String(v)}</>;
}

function ResultTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return null;
  const cols = Object.keys(rows[0]);
  return (
    <div className="mt-3 max-h-80 overflow-auto rounded border">
      <Table className="text-xs">
        <thead>
          <tr>
            {cols.map((c) => (
              <Th key={c}>{label(c)}</Th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 50).map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <Td key={c} className="tabular">
                  <Cell v={r[c]} />
                </Td>
              ))}
            </tr>
          ))}
        </tbody>
      </Table>
      {rows.length > 50 && <div className="p-2 text-xs text-slate-500">Showing 50 of {rows.length} rows</div>}
    </div>
  );
}

export default function AssistantPage() {
  const { environment } = useSession();
  const status = useApi<{ provider: string; suggestions: string[] }>("/api/ai/status");
  const [runId, setRunId] = useState<number | "">("");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), [messages]);

  const ask = async (q: string) => {
    if (!q.trim()) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setQuestion("");
    setBusy(true);
    try {
      const answer = await api.post<Answer>("/api/ai/ask", { question: q, run_id: runId || null, environment: environment || null });
      setMessages((m) => [...m, { role: "assistant", answer }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "error", text: e instanceof Error ? e.message : String(e) }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="AI Assistant"
        subtitle="Ask questions about reconciliation results. Answers are grounded in the reconciliation database."
        actions={
          <>
            <RunPicker value={runId} onChange={setRunId} />
            {status.data && <Badge>Provider: {status.data.provider}</Badge>}
          </>
        }
      />
      <Card className="flex h-[calc(100vh-190px)] flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {messages.length === 0 && (
            <div className="mx-auto max-w-2xl pt-10 text-center">
              <Bot className="mx-auto h-10 w-10 text-primary" />
              <h2 className="mt-3 font-semibold text-secondary">How can I help with your migration?</h2>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {status.data?.suggestions.map((s) => (
                  <button key={s} onClick={() => ask(s)} className="rounded-full border border-primary-100 bg-primary-50 px-3 py-1.5 text-sm text-primary hover:bg-primary-100">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="flex justify-end gap-2">
                <div className="max-w-2xl rounded-lg bg-primary px-4 py-2 text-sm text-white">{m.text}</div>
                <User className="mt-1 h-5 w-5 text-slate-400" />
              </div>
            ) : m.role === "error" ? (
              <div key={i} className="rounded-md bg-red-50 px-4 py-2 text-sm text-red-700">
                {m.text}
              </div>
            ) : (
              <div key={i} className="flex gap-2">
                <Bot className="mt-1 h-5 w-5 shrink-0 text-primary" />
                <div className="min-w-0 max-w-4xl flex-1 rounded-lg border bg-slate-50 px-4 py-3 text-sm">
                  <p className="whitespace-pre-line text-slate-800">{m.answer.answer}</p>
                  <ResultTable rows={m.answer.table} />
                  <div className="mt-2 text-[11px] text-slate-400">
                    intent: {m.answer.intent} · provider: {m.answer.provider}
                  </div>
                </div>
              </div>
            ),
          )}
          {busy && <div className="text-sm text-slate-500">Analysing…</div>}
          <div ref={bottom} />
        </div>
        <form
          className="flex gap-2 border-t p-3"
          onSubmit={(e) => {
            e.preventDefault();
            ask(question);
          }}
        >
          <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. Why did reconciliation fail?" />
          <Button type="submit" loading={busy} disabled={!question.trim()}>
            <Send className="h-4 w-4" /> Ask
          </Button>
        </form>
      </Card>
    </>
  );
}
