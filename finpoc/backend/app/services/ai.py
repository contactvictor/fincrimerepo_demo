"""AI reconciliation assistant.

Every answer is grounded in data computed by deterministic "tools" over the reconciliation store.
If Azure OpenAI or Anthropic credentials are configured, the LLM rephrases the grounded facts;
otherwise the built-in narrative generator is used, so the assistant always works offline.
"""
import json
import logging
import re
from collections import Counter

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import MigrationRun, ReconException
from . import analytics
from .workflow import OPEN_STATUSES

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a Financial Crime migration reconciliation assistant for a bank. Answer ONLY using the "
    "JSON facts provided. Be concise, quantitative and audit-friendly. If the facts do not contain "
    "the answer, say so. Never invent record identifiers or numbers."
)

DOMAIN_WORDS = {
    "customer": "customer", "customers": "customer", "account": "account", "accounts": "account",
    "balance": "balance", "balances": "balance", "transaction": "transaction", "transactions": "transaction",
    "aml": "aml", "kyc": "kyc", "sanction": "sanctions", "sanctions": "sanctions", "audit": "audit",
}


def provider_name() -> str:
    s = get_settings()
    if s.azure_openai_endpoint and s.azure_openai_api_key and s.azure_openai_deployment:
        return "azure-openai"
    if s.anthropic_api_key:
        return "anthropic"
    return "built-in"


def _llm(question: str, facts: dict) -> str | None:
    s = get_settings()
    provider = provider_name()
    if provider == "built-in":
        return None
    content = f"Question: {question}\n\nFacts (JSON):\n{json.dumps(facts, default=str)[:12000]}"
    try:
        if provider == "azure-openai":
            url = (f"{s.azure_openai_endpoint.rstrip('/')}/openai/deployments/{s.azure_openai_deployment}"
                   f"/chat/completions?api-version={s.azure_openai_api_version}")
            resp = httpx.post(url, headers={"api-key": s.azure_openai_api_key}, timeout=30, json={
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}],
                "temperature": 0.1, "max_tokens": 600,
            })
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        resp = httpx.post("https://api.anthropic.com/v1/messages", timeout=30, headers={
            "x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01",
        }, json={"model": s.anthropic_model, "max_tokens": 600, "system": SYSTEM_PROMPT,
                 "messages": [{"role": "user", "content": content}]})
        resp.raise_for_status()
        return "".join(block.get("text", "") for block in resp.json()["content"])
    except Exception as exc:  # fall back to deterministic narrative
        log.warning("LLM provider %s failed: %s", provider, exc)
        return None


def _exc_query(ids: list[int], domain: str | None = None, open_only: bool = False):
    stmt = select(ReconException).where(ReconException.run_id.in_(ids))
    if domain:
        stmt = stmt.where(ReconException.domain == domain)
    if open_only:
        stmt = stmt.where(ReconException.status.in_(OPEN_STATUSES))
    return stmt


def _group(rows, attr) -> list[tuple[str, int]]:
    return Counter(getattr(r, attr) for r in rows).most_common()


def _fmt_groups(groups: list[tuple[str, int]]) -> str:
    return ", ".join(f"{k.replace('_', ' ').lower()} ({v})" for k, v in groups) or "none"


def _exc_rows(rows: list[ReconException], limit: int = 25) -> list[dict]:
    return [{"code": e.code, "run_id": e.run_id, "domain": e.domain, "category": e.category,
             "severity": e.severity, "root_cause": e.root_cause, "record_key": e.record_key,
             "field": e.field, "source": e.source_value, "target": e.target_value,
             "status": e.status} for e in rows[:limit]]


def tool_why_failed(db: Session, ids: list[int], domain: str | None) -> dict:
    results = [r for r in analytics.rule_results(db, ids) if not domain or r.domain == domain]
    failed = [r for r in results if not r.passed]
    excs = list(db.scalars(_exc_query(ids, domain)))
    by_domain = _group(excs, "domain")
    causes = _group(excs, "root_cause")
    answer = (f"{len(failed)} of {len(results)} reconciliation rules failed"
              + (f" for {domain}" if domain else "") + ". "
              + (f"Failures concentrate in {_fmt_groups(by_domain[:3])}. " if by_domain else "")
              + f"Leading root causes: {_fmt_groups(causes[:3])}. "
              + ("Top failed rules: " + "; ".join(f"{r.rule_name} (actual {r.actual}, expected {r.expected})"
                                                 for r in failed[:4]) + "." if failed else ""))
    return {"answer": answer, "facts": {"failed_rules": [
        {"rule": r.rule_name, "domain": r.domain, "actual": r.actual, "expected": r.expected,
         "detail": r.detail} for r in failed], "exceptions_by_domain": by_domain,
        "root_causes": causes},
        "table": [{"rule": r.rule_name, "domain": r.domain, "category": r.category,
                   "actual": r.actual, "expected": r.expected} for r in failed]}


def tool_highest_mismatch(db: Session, ids: list[int], domain: str | None) -> dict:
    top = analytics.top_balance_variances(db, ids, 10)
    if not top:
        return {"answer": "No balance variances were found.", "facts": {}, "table": []}
    lead = top[0]
    answer = (f"Account {lead['account_id']} has the highest balance mismatch with total absolute variance "
              f"{lead['total_abs_variance']:,.2f} across {len(lead['fields'])} balance field(s). "
              f"The top {len(top)} accounts account for {sum(t['total_abs_variance'] for t in top):,.2f} of variance.")
    table = [{"account_id": t["account_id"], "run_id": t["run_id"], "total_abs_variance": t["total_abs_variance"],
              "fields": ", ".join(f"{f['field']} {f['difference']:+,.2f}" for f in t["fields"])} for t in top]
    return {"answer": answer, "facts": {"top_accounts": table}, "table": table}


def tool_domain_failures(db: Session, ids: list[int], domain: str) -> dict:
    excs = list(db.scalars(_exc_query(ids, domain)))
    if not excs:
        return {"answer": f"No {domain.upper()} reconciliation failures were found.", "facts": {}, "table": []}
    keys = {e.record_key for e in excs if e.record_key}
    fields = Counter(e.field for e in excs if e.field and not e.field.startswith("rule:")).most_common(5)
    open_count = sum(e.status in OPEN_STATUSES for e in excs)
    detail = ""
    if fields:
        f, c = fields[0]
        missing = sum(1 for e in excs if e.field == f and e.target_value is None)
        detail = (f" The most common failure is '{f}' ({c} records"
                  + (f", {missing} missing in target" if missing else "") + ").")
    label = "AML cases" if domain == "aml" else f"{domain} records"
    answer = (f"{len(keys)} {label} failed migration with {len(excs)} exception(s); {open_count} remain open."
              f"{detail} Severity: {_fmt_groups(_group(excs, 'severity'))}. "
              f"Root causes: {_fmt_groups(_group(excs, 'root_cause'))}.")
    return {"answer": answer, "facts": {"failed_records": len(keys), "fields": fields,
                                        "severity": _group(excs, "severity"),
                                        "root_causes": _group(excs, "root_cause")},
            "table": _exc_rows(sorted(excs, key=lambda e: ["CRITICAL", "HIGH", "MEDIUM", "LOW"].index(e.severity)))}


def tool_balance_root_cause(db: Session, ids: list[int], domain: str | None) -> dict:
    excs = [e for e in db.scalars(_exc_query(ids, "balance")) if e.category == "BALANCE_VARIANCE"]
    if not excs:
        return {"answer": "No balance variances were detected.", "facts": {}, "table": []}
    by_cause: dict[str, dict] = {}
    for e in excs:
        item = by_cause.setdefault(e.root_cause, {"root_cause": e.root_cause, "count": 0, "abs_variance": 0.0,
                                                  "example": e.root_cause_detail, "_max": 0.0})
        item["count"] += 1
        item["abs_variance"] += abs(e.variance)
        if abs(e.variance) > item["_max"]:
            item["_max"], item["example"] = abs(e.variance), f"{e.record_key}: {e.root_cause_detail}"
    table = sorted(by_cause.values(), key=lambda x: -x["abs_variance"])
    total = sum(t["abs_variance"] for t in table)
    lead = table[0]
    answer = (f"{len(excs)} balance variances totalling {total:,.2f}. The dominant root cause is "
              f"{lead['root_cause'].replace('_', ' ').lower()} ({lead['count']} items, {lead['abs_variance']:,.2f}, "
              f"{100 * lead['abs_variance'] / total:.1f}% of value): {lead['example']}")
    for t in table:
        t["abs_variance"] = round(t["abs_variance"], 2)
        t.pop("_max")
    return {"answer": answer, "facts": {"by_root_cause": table}, "table": table}


def tool_overview(db: Session, ids: list[int], domain: str | None) -> dict:
    runs = list(db.scalars(select(MigrationRun).where(MigrationRun.id.in_(ids))))
    excs = list(db.scalars(_exc_query(ids, domain)))
    open_count = sum(e.status in OPEN_STATUSES for e in excs)
    stats = analytics.domain_stats(db, ids)
    worst = sorted([s for s in stats if s["match_pct"] is not None], key=lambda s: s["match_pct"])[:3]
    answer = (f"{len(runs)} migration run(s) in scope; {len(excs)} exceptions ({open_count} open). "
              f"Severity: {_fmt_groups(_group(excs, 'severity'))}. "
              + ("Lowest match rates: " + ", ".join(f"{s['domain']} {s['match_pct']}%" for s in worst) + "."
                 if worst else ""))
    table = [{"run": r.name, "status": r.status, "reconciliation_pct": r.reconciliation_pct,
              "signoff": r.signoff_status} for r in runs]
    return {"answer": answer, "facts": {"runs": table, "domains": stats}, "table": table}


INTENTS = [
    ("highest_mismatch", re.compile(r"(highest|largest|top|biggest).*(mismatch|variance|difference)"), tool_highest_mismatch),
    ("balance_root_cause", re.compile(r"(root cause|why|cause).*(balance|variance)|balance.*(root cause)"), tool_balance_root_cause),
    ("why_failed", re.compile(r"(why|reason).*(fail|break|mismatch)|fail(ed|ure)?.*(rule|reconciliation)"), tool_why_failed),
]


def detect_domain(question: str) -> str | None:
    for word in re.findall(r"[a-z]+", question.lower()):
        if word in DOMAIN_WORDS:
            return DOMAIN_WORDS[word]
    return None


def ask(db: Session, question: str, run_id: int | None = None, environment: str | None = None) -> dict:
    ids = analytics.run_ids(db, environment, run_id)
    q = question.lower()
    domain = detect_domain(q)
    intent, tool = "overview", tool_overview
    for name, pattern, fn in INTENTS:
        if pattern.search(q):
            intent, tool = name, fn
            break
    else:
        if domain and re.search(r"fail|issue|exception|mismatch|missing|error|break", q):
            intent, tool = f"{domain}_failures", lambda db_, ids_, d: tool_domain_failures(db_, ids_, d)
    if intent == "why_failed" and domain and domain != "balance" and "rule" not in q:
        intent = f"{domain}_failures"
        result = tool_domain_failures(db, ids, domain)
    else:
        result = tool(db, ids, domain)
    llm_answer = _llm(question, {"intent": intent, "grounded_answer": result["answer"], **result["facts"]})
    return {"question": question, "intent": intent, "provider": provider_name() if llm_answer else "built-in",
            "answer": llm_answer or result["answer"], "table": result["table"][:50]}


def explain_exception(db: Session, exc: ReconException) -> dict:
    similar = db.scalar(select(func.count()).select_from(ReconException).where(
        ReconException.run_id == exc.run_id, ReconException.domain == exc.domain,
        ReconException.root_cause == exc.root_cause)) or 0
    steps = {
        "TRANSFORMATION_ISSUE": "Review the transformation logic (scaling, rounding, sign, date formats) for this field and re-run the affected batch.",
        "MISSING_RECORDS": "Check extraction filters and reject logs for the key; re-extract and load the missing record.",
        "SOURCE_ISSUE": "Raise a data-quality ticket with the source system owner and confirm the golden value.",
        "MAPPING_ISSUE": "Update the source-to-target mapping / reference-data translation table and reload.",
        "LOAD_ISSUE": "Inspect load batch logs for partial commits or re-runs; enforce idempotent loads.",
        "DATA_QUALITY_ISSUE": "Apply the agreed cleansing rule and document the variance for business sign-off.",
    }
    facts = {"exception": _exc_rows([exc])[0], "detail": exc.root_cause_detail,
             "similar_exceptions_same_cause": similar, "recommended_action": steps.get(exc.root_cause, "")}
    base = (f"{exc.root_cause.replace('_', ' ').title()}: {exc.root_cause_detail} "
            f"{similar} exception(s) in the {exc.domain} domain share this root cause. "
            f"Recommended action: {steps.get(exc.root_cause, 'Investigate with the migration team.')}")
    llm = _llm(f"Explain the root cause of exception {exc.code} and recommend remediation.", facts)
    return {"code": exc.code, "root_cause": exc.root_cause, "explanation": llm or base,
            "recommended_action": steps.get(exc.root_cause, ""), "similar": similar,
            "provider": provider_name() if llm else "built-in"}


def executive_narrative(db: Session, run: MigrationRun) -> str:
    result = tool_overview(db, [run.id], None)
    why = tool_why_failed(db, [run.id], None)
    base = (f"Run '{run.name}' ({run.source_system} to {run.target_system}, {run.environment}) reconciled "
            f"{run.records_processed:,} source records at {run.reconciliation_pct:.2f}% record-level match. "
            f"{result['answer']} {why['answer']}")
    return _llm("Write a 4-sentence executive summary of this migration reconciliation.",
                {"grounded_summary": base, **result["facts"]}) or base
