export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const TOKEN_KEY = "fcr_token";

export const tokenStore = {
  get: () => (typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY)),
  set: (t: string) => window.localStorage.setItem(TOKEN_KEY, t),
  clear: () => window.localStorage.removeItem(TOKEN_KEY),
};

function headers(extra?: HeadersInit): HeadersInit {
  const token = tokenStore.get();
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(extra || {}) };
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    tokenStore.clear();
    window.location.href = "/login";
  }
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function qs(params: Record<string, string | number | boolean | null | undefined>) {
  const s = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  });
  const out = s.toString();
  return out ? `?${out}` : "";
}

export const api = {
  get: <T>(path: string) => fetch(path, { headers: headers() }).then((r) => handle<T>(r)),
  post: <T>(path: string, body?: unknown) =>
    fetch(path, {
      method: "POST",
      headers: headers({ "Content-Type": "application/json" }),
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then((r) => handle<T>(r)),
  put: <T>(path: string, body: unknown) =>
    fetch(path, {
      method: "PUT",
      headers: headers({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    }).then((r) => handle<T>(r)),
  del: <T>(path: string) => fetch(path, { method: "DELETE", headers: headers() }).then((r) => handle<T>(r)),
  form: <T>(path: string, form: FormData) =>
    fetch(path, { method: "POST", headers: headers(), body: form }).then((r) => handle<T>(r)),
  login: async (username: string, password: string) => {
    const body = new URLSearchParams({ username, password });
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    return handle<{ access_token: string; user: Me }>(res);
  },
  download: async (path: string, fallbackName: string) => {
    const res = await fetch(path, { headers: headers() });
    if (!res.ok) await handle(res);
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const name = /filename="?([^"]+)"?/.exec(cd)?.[1] || fallbackName;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  },
};

export type Me = {
  id: number;
  username: string;
  full_name: string;
  email: string;
  role: string;
  active: boolean;
  permissions: string[];
  domains: string[] | null;
};

export type Run = {
  id: number;
  name: string;
  description: string;
  source_system: string;
  target_system: string;
  environment: string;
  status: string;
  progress: number;
  records_processed: number;
  reconciliation_pct: number;
  signoff_status: string;
  created_by: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type DomainStat = {
  domain: string;
  total: number;
  MATCHED: number;
  MISMATCHED: number;
  MISSING_IN_TARGET: number;
  MISSING_IN_SOURCE: number;
  exceptions: number;
  open_exceptions: number;
  source_count: number;
  target_count: number;
  match_pct: number | null;
};

export type RuleResult = {
  rule_id: number;
  rule_name: string;
  category: string;
  domain: string;
  passed: boolean;
  actual: string;
  expected: string;
  detail: string;
};

export type SignOff = { id: number; area: string; decision: string; actor: string; role: string; comment: string; at: string };

export type ExceptionItem = {
  id: number;
  code: string;
  run_id: number;
  domain: string;
  category: string;
  severity: string;
  root_cause: string;
  root_cause_detail: string;
  record_key: string | null;
  field: string | null;
  source_value: string | null;
  target_value: string | null;
  variance: number;
  description: string;
  owner: string | null;
  status: string;
  resolution: string;
  created_at: string;
  updated_at: string;
};

export type ExceptionDetail = ExceptionItem & {
  history: { from_status: string | null; to_status: string; actor: string; comment: string; at: string }[];
  allowed_transitions: string[];
};

export type FieldDiff = { field: string; source: unknown; target: unknown; difference: number };

export type RecordItem = {
  id: number;
  domain: string;
  record_key: string;
  status: string;
  source_data: Record<string, unknown> | null;
  target_data: Record<string, unknown> | null;
  field_differences: FieldDiff[];
  variance: number;
};

export type Summary = { domain: string; metric: string; source_value: number; target_value: number; difference: number; matched: boolean };

export type Rule = {
  id: number;
  name: string;
  description: string;
  category: string;
  domain: string;
  params: Record<string, unknown>;
  severity: string;
  active: boolean;
};

export type ReportItem = {
  id: number;
  run_id: number;
  report_type: string;
  file_format: string;
  filename: string;
  sha256: string;
  size_bytes: number;
  created_by: string;
  created_at: string;
};

export type Meta = {
  source_systems: string[];
  target_systems: string[];
  environments: string[];
  domains: Record<string, { key: string; fields: string[]; numeric: string[] }>;
  signoff_areas: Record<string, string[]>;
  sql_dialects: Record<string, string>;
};
