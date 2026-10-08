"""Business rules engine. Rules are structured parameters (never evaluated code)."""
import operator
from dataclasses import dataclass

from ..constants import DOMAIN_SPECS, RuleCategory
from .recon_engine import DomainResult, _is_null, values_equal

OPERATORS = {
    "<=": operator.le, "<": operator.lt, "==": operator.eq,
    ">=": operator.ge, ">": operator.gt, "!=": operator.ne,
}


@dataclass
class RuleOutcome:
    passed: bool
    actual: str
    expected: str
    detail: str


class RuleError(ValueError):
    pass


def validate_params(category: str, domain: str, params: dict) -> None:
    if domain not in DOMAIN_SPECS:
        raise RuleError(f"Unknown domain '{domain}'")
    spec = DOMAIN_SPECS[domain]
    if category == RuleCategory.RECONCILIATION.value:
        if not params.get("metric"):
            raise RuleError("RECONCILIATION rules need a 'metric' (e.g. record_count)")
    elif category == RuleCategory.THRESHOLD.value:
        if params.get("field") not in spec["numeric"]:
            raise RuleError(f"THRESHOLD 'field' must be one of {spec['numeric']}")
        if params.get("operator", "<=") not in OPERATORS:
            raise RuleError(f"'operator' must be one of {list(OPERATORS)}")
        if params.get("measure", "total_abs_variance") not in {"total_abs_variance", "max_abs_variance"}:
            raise RuleError("'measure' must be total_abs_variance or max_abs_variance")
        float(params.get("value", 0))
    elif category == RuleCategory.PERCENTAGE_THRESHOLD.value:
        float(params.get("max_mismatch_pct", 0.01))
    elif category == RuleCategory.COMPLIANCE.value:
        if not params.get("filter_field") or not params.get("required_fields"):
            raise RuleError("COMPLIANCE rules need 'filter_field', 'filter_values', 'required_fields'")
    elif category == RuleCategory.COMPLETENESS.value:
        pass
    else:
        raise RuleError(f"Unknown rule category '{category}'")


def evaluate(category: str, domain: str, params: dict, result: DomainResult) -> RuleOutcome:
    validate_params(category, domain, params)
    spec = DOMAIN_SPECS[domain]

    if category == RuleCategory.RECONCILIATION.value:
        metric = params["metric"]
        summary = next((s for s in result.summaries if s.metric == metric), None)
        if summary is None:
            raise RuleError(f"Metric '{metric}' not produced for domain '{domain}'")
        tol = float(params.get("tolerance", 0))
        return RuleOutcome(
            summary.matched(tol), f"{summary.target_value:,.2f}", f"{summary.source_value:,.2f}",
            f"Source.{metric}={summary.source_value:,.2f} vs Target.{metric}={summary.target_value:,.2f}",
        )

    if category == RuleCategory.THRESHOLD.value:
        field = params["field"]
        measure = params.get("measure", "total_abs_variance")
        op, limit = params.get("operator", "<="), float(params.get("value", 0))
        variances = [abs(d["difference"]) for r in result.records for d in r.field_differences
                     if d["field"] == field]
        actual = (sum(variances) if measure == "total_abs_variance" else max(variances, default=0.0))
        passed = OPERATORS[op](round(actual, 6), limit)
        return RuleOutcome(passed, f"{actual:,.2f}", f"{op} {limit:,.2f}",
                           f"{measure} on {field} across {len(variances)} variant record(s)")

    if category == RuleCategory.PERCENTAGE_THRESHOLD.value:
        limit = float(params.get("max_mismatch_pct", 0.01))
        total = result.total_records
        mismatched = total - result.matched_records
        pct = 100.0 * mismatched / total if total else 0.0
        return RuleOutcome(pct < limit, f"{pct:.4f}%", f"< {limit}%",
                           f"{mismatched} of {total} records not fully reconciled")

    if category == RuleCategory.COMPLIANCE.value:
        f_field = params["filter_field"]
        f_values = {str(v).upper() for v in params.get("filter_values", [])}
        required = params["required_fields"]
        by_key = {r.record_key: r for r in result.records}
        in_scope = failures = 0
        failed_keys: list[str] = []
        for rec in by_key.values():
            src = rec.source_data
            if not src or str(src.get(f_field, "")).upper() not in f_values:
                continue
            in_scope += 1
            tgt = rec.target_data
            numeric = set(spec["numeric"])
            ok = tgt is not None and all(
                not _is_null(tgt.get(f)) and values_equal(src.get(f), tgt.get(f), f in numeric)
                for f in required
            )
            if not ok:
                failures += 1
                failed_keys.append(rec.record_key)
        sample = ", ".join(failed_keys[:5])
        return RuleOutcome(failures == 0, f"{failures} non-compliant", "0 non-compliant",
                           f"{in_scope} in-scope record(s) where {f_field} in {sorted(f_values)}; "
                           f"required {required} migrated unchanged"
                           + (f". Examples: {sample}" if sample else ""))

    # COMPLETENESS
    mandatory = params.get("mandatory_fields") or spec["mandatory"]
    tgt = result.target_df
    nulls = {}
    for col in mandatory:
        if col in tgt.columns and len(tgt):
            count = int(tgt[col].isna().sum() + (tgt[col].astype(str).str.strip() == "").sum())
        else:
            count = len(tgt)
        if count:
            nulls[col] = count
    total = sum(nulls.values())
    return RuleOutcome(total == 0, f"{total} null value(s)", "0 null values",
                       "Null mandatory fields in target: "
                       + (", ".join(f"{k}={v}" for k, v in nulls.items()) or "none"))
