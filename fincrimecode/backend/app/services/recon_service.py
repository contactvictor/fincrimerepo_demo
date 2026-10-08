"""Persists reconciliation results, rule outcomes and exceptions for a migration run."""
from collections import Counter, defaultdict

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..constants import DOMAIN_SPECS, ExceptionCategory, RootCause, RuleCategory, Severity
from ..models import (
    MigrationRun, ReconException, ReconSummary, RecordResult, Rule, RuleResult, SourceRecord,
    TargetRecord, utcnow,
)
from . import rules_engine
from .audit import log_action
from .recon_engine import DomainResult, ExceptionDraft, reconcile_domain


def _load(db: Session, model, run_id: int, domain: str) -> list[dict]:
    return list(db.scalars(select(model.data).where(model.run_id == run_id, model.domain == domain)))


def _rule_root_cause(rule: Rule, result: DomainResult) -> str:
    if rule.category == RuleCategory.COMPLETENESS.value:
        return RootCause.TRANSFORMATION_ISSUE.value
    if rule.category == RuleCategory.COMPLIANCE.value:
        return RootCause.MAPPING_ISSUE.value
    if rule.category == RuleCategory.RECONCILIATION.value and rule.params.get("metric") in {
        "record_count", "distinct_keys"
    }:
        return RootCause.LOAD_ISSUE.value
    causes = Counter(e.root_cause for e in result.exceptions)
    return causes.most_common(1)[0][0] if causes else RootCause.DATA_QUALITY_ISSUE.value


def recompute_run_metrics(db: Session, run: MigrationRun) -> None:
    total = db.scalar(select(func.count()).select_from(RecordResult).where(RecordResult.run_id == run.id)) or 0
    matched = db.scalar(select(func.count()).select_from(RecordResult).where(
        RecordResult.run_id == run.id, RecordResult.status == "MATCHED")) or 0
    run.reconciliation_pct = round(100.0 * matched / total, 4) if total else 0.0
    run.records_processed = db.scalar(
        select(func.count()).select_from(SourceRecord).where(SourceRecord.run_id == run.id)) or 0


def run_reconciliation(db: Session, run: MigrationRun, actor: str,
                       domains: list[str] | None = None) -> dict:
    settings = get_settings()
    domains = domains or list(DOMAIN_SPECS)
    run.status = "RECONCILING"
    run.started_at = run.started_at or utcnow()
    db.flush()

    previous = {
        (e.domain, e.category, e.record_key, e.field): e
        for e in db.scalars(select(ReconException).where(
            ReconException.run_id == run.id, ReconException.domain.in_(domains)))
    }
    carry = {sig: (e.status, e.owner, e.resolution, e.created_at) for sig, e in previous.items()}
    for model in (ReconSummary, RecordResult, RuleResult, ReconException):
        db.execute(delete(model).where(model.run_id == run.id, model.domain.in_(domains)))
    db.flush()

    existing_codes = db.scalars(select(ReconException.code).where(ReconException.run_id == run.id))
    seq = max((int(c.rsplit("-", 1)[1]) for c in existing_codes), default=0)
    rules = list(db.scalars(select(Rule).where(Rule.active.is_(True), Rule.domain.in_(domains))))
    rules_by_domain: dict[str, list[Rule]] = defaultdict(list)
    for rule in rules:
        rules_by_domain[rule.domain].append(rule)

    stats: dict[str, dict] = {}
    now = utcnow()
    for domain in domains:
        result = reconcile_domain(domain, _load(db, SourceRecord, run.id, domain),
                                  _load(db, TargetRecord, run.id, domain),
                                  settings.numeric_tolerance, settings.critical_variance_amount)
        db.execute(insert(ReconSummary), [
            {"run_id": run.id, "domain": domain, "metric": s.metric, "source_value": s.source_value,
             "target_value": s.target_value, "difference": s.difference,
             "matched": s.matched(settings.numeric_tolerance)}
            for s in result.summaries
        ])
        if result.records:
            db.execute(insert(RecordResult), [
                {"run_id": run.id, "domain": domain, "record_key": r.record_key, "status": r.status,
                 "source_data": r.source_data, "target_data": r.target_data,
                 "field_differences": r.field_differences, "variance": r.variance}
                for r in result.records
            ])

        drafts: list[ExceptionDraft] = list(result.exceptions)
        rules_passed = 0
        for rule in rules_by_domain[domain]:
            try:
                outcome = rules_engine.evaluate(rule.category, domain, rule.params, result)
            except rules_engine.RuleError as err:
                outcome = rules_engine.RuleOutcome(False, "error", "", str(err))
            rules_passed += outcome.passed
            db.add(RuleResult(run_id=run.id, rule_id=rule.id, rule_name=rule.name,
                              category=rule.category, domain=domain, passed=outcome.passed,
                              actual=outcome.actual, expected=outcome.expected, detail=outcome.detail))
            if not outcome.passed:
                drafts.append(ExceptionDraft(
                    domain=domain, category=ExceptionCategory.RULE_FAILURE.value,
                    severity=rule.severity or Severity.HIGH.value,
                    root_cause=_rule_root_cause(rule, result),
                    root_cause_detail=outcome.detail,
                    description=f"Rule '{rule.name}' failed: actual {outcome.actual}, expected {outcome.expected}",
                    field=f"rule:{rule.id}",
                ))

        rows = []
        for draft in drafts:
            seq += 1
            status, owner, resolution, created = carry.get(draft.signature, ("DETECTED", None, "", now))
            rows.append({
                "code": f"EXC-{run.id:04d}-{seq:06d}", "run_id": run.id, "domain": domain,
                "category": draft.category, "severity": draft.severity,
                "root_cause": draft.root_cause, "root_cause_detail": draft.root_cause_detail,
                "record_key": draft.record_key, "field": draft.field,
                "source_value": draft.source_value, "target_value": draft.target_value,
                "variance": draft.variance, "description": draft.description, "owner": owner,
                "status": status, "resolution": resolution, "created_at": created, "updated_at": now,
            })
        if rows:
            db.execute(insert(ReconException), rows)

        stats[domain] = {
            "records": result.total_records, "matched": result.matched_records,
            "match_pct": result.match_pct, "exceptions": len(drafts),
            "rules_total": len(rules_by_domain[domain]), "rules_passed": rules_passed,
        }

    recompute_run_metrics(db, run)
    run.status = "COMPLETED"
    run.progress = 100.0
    run.completed_at = utcnow()
    log_action(db, actor, "RECONCILIATION_EXECUTED", "migration_run", run.id,
               {"domains": domains, "reconciliation_pct": run.reconciliation_pct})
    db.flush()
    return {"run_id": run.id, "reconciliation_pct": run.reconciliation_pct, "domains": stats}
