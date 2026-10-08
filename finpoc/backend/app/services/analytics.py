"""Read-side aggregations shared by dashboards, reports and the AI assistant."""
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..constants import DOMAIN_SPECS
from ..models import (
    MigrationRun, ReconException, ReconSummary, RecordResult, RuleResult, SourceRecord,
    TargetRecord, utcnow,
)
from .workflow import OPEN_STATUSES


def run_ids(db: Session, environment: str | None = None, run_id: int | None = None) -> list[int]:
    stmt = select(MigrationRun.id)
    if run_id:
        stmt = stmt.where(MigrationRun.id == run_id)
    if environment:
        stmt = stmt.where(MigrationRun.environment == environment)
    return list(db.scalars(stmt))


def domain_stats(db: Session, ids: list[int]) -> list[dict]:
    rows = db.execute(
        select(RecordResult.domain, RecordResult.status, func.count())
        .where(RecordResult.run_id.in_(ids)).group_by(RecordResult.domain, RecordResult.status)
    ).all()
    agg: dict[str, dict] = {d: {"domain": d, "total": 0, "MATCHED": 0, "MISMATCHED": 0,
                                "MISSING_IN_TARGET": 0, "MISSING_IN_SOURCE": 0} for d in DOMAIN_SPECS}
    for domain, status, count in rows:
        agg[domain]["total"] += count
        agg[domain][status] = agg[domain].get(status, 0) + count
    exc_rows = db.execute(
        select(ReconException.domain, func.count(),
               func.sum(case((ReconException.status.in_(OPEN_STATUSES), 1), else_=0)))
        .where(ReconException.run_id.in_(ids)).group_by(ReconException.domain)
    ).all()
    for domain, total, open_count in exc_rows:
        agg[domain]["exceptions"] = total
        agg[domain]["open_exceptions"] = int(open_count or 0)
    src = dict(db.execute(select(SourceRecord.domain, func.count()).where(SourceRecord.run_id.in_(ids))
                          .group_by(SourceRecord.domain)).all())
    tgt = dict(db.execute(select(TargetRecord.domain, func.count()).where(TargetRecord.run_id.in_(ids))
                          .group_by(TargetRecord.domain)).all())
    out = []
    for d, item in agg.items():
        item.setdefault("exceptions", 0)
        item.setdefault("open_exceptions", 0)
        item["source_count"] = src.get(d, 0)
        item["target_count"] = tgt.get(d, 0)
        item["match_pct"] = round(100.0 * item["MATCHED"] / item["total"], 2) if item["total"] else None
        out.append(item)
    return out


def heatmap(db: Session, ids: list[int]) -> list[dict]:
    """Domain x reconciliation level pass-rate (%)."""
    l1 = defaultdict(lambda: [0, 0])
    for domain, matched in db.execute(select(ReconSummary.domain, ReconSummary.matched)
                                      .where(ReconSummary.run_id.in_(ids))):
        l1[domain][0] += int(matched)
        l1[domain][1] += 1
    l2 = defaultdict(lambda: [0, 0])
    l3 = defaultdict(lambda: [0, 0])
    for domain, status, diffs in db.execute(
            select(RecordResult.domain, RecordResult.status, RecordResult.field_differences)
            .where(RecordResult.run_id.in_(ids))):
        l2[domain][0] += status == "MATCHED"
        l2[domain][1] += 1
        if status in {"MATCHED", "MISMATCHED"}:
            n_fields = len(DOMAIN_SPECS[domain]["fields"])
            l3[domain][0] += n_fields - len(diffs or [])
            l3[domain][1] += n_fields

    def pct(pair):
        return round(100.0 * pair[0] / pair[1], 2) if pair[1] else None

    return [{"domain": d, "L1": pct(l1[d]), "L2": pct(l2[d]), "L3": pct(l3[d])} for d in DOMAIN_SPECS]


def exception_breakdown(db: Session, ids: list[int], column) -> list[dict]:
    rows = db.execute(select(column, func.count()).where(ReconException.run_id.in_(ids))
                      .group_by(column).order_by(func.count().desc())).all()
    return [{"name": k, "count": v} for k, v in rows]


def exception_trend(db: Session, ids: list[int], days: int = 21) -> list[dict]:
    from ..models import ExceptionHistory

    start = (utcnow() - timedelta(days=days - 1)).date()
    buckets = {(start + timedelta(days=i)).isoformat(): {"date": (start + timedelta(days=i)).isoformat(),
                                                        "detected": 0, "resolved": 0}
               for i in range(days)}
    for (created,) in db.execute(select(ReconException.created_at).where(ReconException.run_id.in_(ids))):
        key = created.date().isoformat()
        if key in buckets:
            buckets[key]["detected"] += 1
    resolved = db.execute(
        select(ExceptionHistory.at).join(ReconException, ReconException.id == ExceptionHistory.exception_id)
        .where(ReconException.run_id.in_(ids), ExceptionHistory.to_status == "RESOLVED"))
    for (at,) in resolved:
        key = at.date().isoformat()
        if key in buckets:
            buckets[key]["resolved"] += 1
    return list(buckets.values())


def summary_metrics(db: Session, ids: list[int]) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(dict)
    rows = db.execute(select(ReconSummary.domain, ReconSummary.metric, func.sum(ReconSummary.source_value),
                             func.sum(ReconSummary.target_value))
                      .where(ReconSummary.run_id.in_(ids))
                      .group_by(ReconSummary.domain, ReconSummary.metric)).all()
    for domain, metric, s, t in rows:
        out[domain][metric] = {"source": round(s or 0, 2), "target": round(t or 0, 2),
                               "difference": round((t or 0) - (s or 0), 2)}
    return out


def top_balance_variances(db: Session, ids: list[int], limit: int = 10) -> list[dict]:
    rows = db.scalars(select(RecordResult).where(RecordResult.run_id.in_(ids), RecordResult.domain == "balance",
                                                RecordResult.variance > 0)
                      .order_by(RecordResult.variance.desc()).limit(limit))
    return [{"run_id": r.run_id, "account_id": r.record_key, "total_abs_variance": r.variance,
             "fields": r.field_differences} for r in rows]


def rule_results(db: Session, ids: list[int]) -> list[RuleResult]:
    return list(db.scalars(select(RuleResult).where(RuleResult.run_id.in_(ids)).order_by(RuleResult.domain)))


def signoff_overview(db: Session, ids: list[int]) -> list[dict]:
    from .signoff import latest_signoffs
    from ..constants import SignOffArea

    out = []
    for run in db.scalars(select(MigrationRun).where(MigrationRun.id.in_(ids)).order_by(MigrationRun.id)):
        latest = latest_signoffs(db, run.id)
        out.append({"run_id": run.id, "run_name": run.name, "status": run.signoff_status,
                    "areas": {a.value: (latest[a.value].decision if a.value in latest else "PENDING")
                              for a in SignOffArea}})
    return out


def field_value_counts(db: Session, ids: list[int], domain: str, field: str, side: str = "target") -> list[dict]:
    model = TargetRecord if side == "target" else SourceRecord
    counts: dict[str, int] = defaultdict(int)
    for (data,) in db.execute(select(model.data).where(model.run_id.in_(ids), model.domain == domain)):
        counts[str(data.get(field))] += 1
    return [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
