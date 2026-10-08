from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import MigrationRun, ReconException, RecordResult, User
from ..schemas import ExceptionOut
from ..security import get_current_user, require
from ..services import analytics
from ..services.workflow import OPEN_STATUSES

router = APIRouter(prefix="/api", tags=["dashboards"])


def _scope(db: Session, environment: str | None, run_id: int | None) -> list[int]:
    return analytics.run_ids(db, environment, run_id)


@router.get("/dashboard/executive")
def executive(environment: str | None = None, run_id: int | None = None, db: Session = Depends(get_db),
              _: User = Depends(require("dashboard:read"))):
    ids = _scope(db, environment, run_id)
    runs = list(db.scalars(select(MigrationRun).where(MigrationRun.id.in_(ids)).order_by(MigrationRun.id)))
    stats = analytics.domain_stats(db, ids)
    total = sum(s["total"] for s in stats)
    matched = sum(s["MATCHED"] for s in stats)
    excs = db.execute(select(ReconException.status, ReconException.severity, func.count())
                      .where(ReconException.run_id.in_(ids))
                      .group_by(ReconException.status, ReconException.severity)).all()
    open_count = sum(c for st, _, c in excs if st in OPEN_STATUSES)
    critical_open = sum(c for st, sev, c in excs if st in OPEN_STATUSES and sev == "CRITICAL")
    signed = sum(r.signoff_status == "APPROVED" for r in runs)
    return {
        "kpis": {
            "migration_progress": round(sum(r.progress for r in runs) / len(runs), 1) if runs else 0,
            "runs": len(runs), "runs_completed": sum(r.status == "COMPLETED" for r in runs),
            "records_processed": sum(r.records_processed for r in runs),
            "reconciliation_pct": round(100.0 * matched / total, 2) if total else 0,
            "exceptions": sum(c for _, _, c in excs), "open_exceptions": open_count,
            "critical_open": critical_open, "signoff_approved": signed,
        },
        "cards": {d["domain"]: d for d in stats},
        "runs": [{"id": r.id, "name": r.name, "status": r.status, "environment": r.environment,
                  "progress": r.progress, "reconciliation_pct": r.reconciliation_pct,
                  "records_processed": r.records_processed, "signoff_status": r.signoff_status,
                  "source_system": r.source_system, "target_system": r.target_system} for r in runs],
        "errors_by_domain": [{"name": s["domain"], "count": s["exceptions"], "open": s["open_exceptions"]}
                             for s in stats],
        "heatmap": analytics.heatmap(db, ids),
        "exception_trend": analytics.exception_trend(db, ids),
        "signoffs": analytics.signoff_overview(db, ids),
        "by_severity": analytics.exception_breakdown(db, ids, ReconException.severity),
        "by_root_cause": analytics.exception_breakdown(db, ids, ReconException.root_cause),
        "by_status": analytics.exception_breakdown(db, ids, ReconException.status),
    }


@router.get("/dashboard/finance")
def finance(environment: str | None = None, run_id: int | None = None, db: Session = Depends(get_db),
            _: User = Depends(require("dashboard:read"))):
    ids = _scope(db, environment, run_id)
    metrics = analytics.summary_metrics(db, ids)
    bal, txn = metrics.get("balance", {}), metrics.get("transaction", {})
    balance_fields = ["current_balance", "available_balance", "ledger_balance", "blocked_balance",
                      "opening_balance", "closing_balance"]
    variance_excs = list(db.scalars(select(ReconException).where(
        ReconException.run_id.in_(ids), ReconException.category == "BALANCE_VARIANCE")))
    return {
        "kpis": {
            "accounts": bal.get("record_count", {}),
            "total_current_balance": bal.get("sum_current_balance", {}),
            "financial_variance": round(sum(abs(e.variance) for e in variance_excs), 2),
            "variance_exceptions": len(variance_excs),
            "debit_total": txn.get("debit_total", {}), "credit_total": txn.get("credit_total", {}),
        },
        "ledger_comparison": [{"name": f.replace("_balance", ""), **bal.get(f"sum_{f}", {})}
                              for f in balance_fields],
        "debit_credit": [{"name": k.replace("_", " "), **txn.get(k, {})}
                         for k in ["debit_total", "credit_total"]],
        "transaction_status": [{"name": k.replace("_count", ""), **txn.get(k, {})}
                               for k in ["posted_count", "pending_count", "reversed_count"]],
        "top_variances": analytics.top_balance_variances(db, ids, 10),
        "variance_by_root_cause": analytics.exception_breakdown(
            db, ids, ReconException.root_cause) if not variance_excs else [
            {"name": rc, "count": sum(1 for e in variance_excs if e.root_cause == rc),
             "value": round(sum(abs(e.variance) for e in variance_excs if e.root_cause == rc), 2)}
            for rc in sorted({e.root_cause for e in variance_excs})],
    }


def _domain_excs(db: Session, ids: list[int], domains: list[str]) -> list[ReconException]:
    return list(db.scalars(select(ReconException).where(ReconException.run_id.in_(ids),
                                                        ReconException.domain.in_(domains))))


@router.get("/dashboard/aml")
def aml(environment: str | None = None, run_id: int | None = None, db: Session = Depends(get_db),
        _: User = Depends(require("dashboard:read"))):
    ids = _scope(db, environment, run_id)
    m = analytics.summary_metrics(db, ids).get("aml", {})
    excs = _domain_excs(db, ids, ["aml"])
    by_field: dict[str, int] = {}
    for e in excs:
        if e.field:
            by_field[e.field] = by_field.get(e.field, 0) + 1
    return {
        "kpis": {"cases": m.get("record_count", {}), "high_risk_cases": m.get("high_risk_cases", {}),
                 "sar_filed": m.get("sar_filed", {}), "watchlist_matches": m.get("watchlist_matches", {}),
                 "failed_cases": len({e.record_key for e in excs if e.record_key}),
                 "open_exceptions": sum(e.status in OPEN_STATUSES for e in excs)},
        "risk_categories": analytics.field_value_counts(db, ids, "aml", "risk_rating", "source"),
        "risk_categories_target": analytics.field_value_counts(db, ids, "aml", "risk_rating", "target"),
        "alert_types": analytics.field_value_counts(db, ids, "aml", "alert_type", "source"),
        "case_status": analytics.field_value_counts(db, ids, "aml", "case_status", "target"),
        "failures_by_field": [{"name": k, "count": v} for k, v in sorted(by_field.items(), key=lambda kv: -kv[1])],
    }


@router.get("/dashboard/compliance")
def compliance(environment: str | None = None, run_id: int | None = None, db: Session = Depends(get_db),
               _: User = Depends(require("dashboard:read"))):
    ids = _scope(db, environment, run_id)
    metrics = analytics.summary_metrics(db, ids)
    kyc, sanc = metrics.get("kyc", {}), metrics.get("sanctions", {})
    excs = _domain_excs(db, ids, ["kyc", "sanctions"])
    missing_docs = sum(1 for e in excs if e.field == "documents_count")
    return {
        "kpis": {"kyc_records": kyc.get("record_count", {}), "pep_customers": kyc.get("pep_customers", {}),
                 "missing_documents": missing_docs, "sanctions_matches": sanc.get("record_count", {}),
                 "open_matches": sanc.get("open_matches", {}),
                 "open_exceptions": sum(e.status in OPEN_STATUSES for e in excs)},
        "kyc_status": analytics.field_value_counts(db, ids, "kyc", "kyc_status", "target"),
        "risk_classification": analytics.field_value_counts(db, ids, "kyc", "risk_classification", "target"),
        "pep_classification": [{"name": "PEP" if k["name"] == "True" else "Non-PEP", "count": k["count"]}
                               for k in analytics.field_value_counts(db, ids, "kyc", "pep_flag", "target")],
        "sanctions_status": analytics.field_value_counts(db, ids, "sanctions", "match_status", "target"),
        "screening_findings": analytics.field_value_counts(db, ids, "sanctions", "finding", "target"),
        "exceptions_by_field": [{"name": f"{e_dom}.{f}", "count": c} for (e_dom, f), c in sorted(
            _count_fields(excs).items(), key=lambda kv: -kv[1])],
    }


def _count_fields(excs: list[ReconException]) -> dict[tuple, int]:
    out: dict[tuple, int] = {}
    for e in excs:
        k = (e.domain, e.field or "record")
        out[k] = out.get(k, 0) + 1
    return out


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    items = db.scalars(select(ReconException).where(ReconException.severity == "CRITICAL",
                                                    ReconException.status.in_(["DETECTED"]))
                       .order_by(ReconException.created_at.desc()).limit(10))
    total = db.scalar(select(func.count()).select_from(ReconException).where(
        ReconException.severity == "CRITICAL", ReconException.status == "DETECTED"))
    return {"unread": total, "items": [ExceptionOut.model_validate(e) for e in items]}


@router.get("/search")
def search(q: str, db: Session = Depends(get_db), _: User = Depends(require("runs:read"))):
    like = f"%{q}%"
    runs = db.scalars(select(MigrationRun).where(MigrationRun.name.ilike(like)).limit(5))
    excs = db.scalars(select(ReconException).where(or_(ReconException.code.ilike(like),
                                                       ReconException.record_key.ilike(like))).limit(10))
    recs = db.scalars(select(RecordResult).where(RecordResult.record_key.ilike(like),
                                                 RecordResult.status != "MATCHED").limit(10))
    return {
        "runs": [{"id": r.id, "name": r.name} for r in runs],
        "exceptions": [{"code": e.code, "domain": e.domain, "description": e.description} for e in excs],
        "records": [{"run_id": r.run_id, "domain": r.domain, "record_key": r.record_key, "status": r.status}
                    for r in recs],
    }
