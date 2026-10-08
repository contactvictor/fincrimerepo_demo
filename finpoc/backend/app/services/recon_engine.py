"""Pure reconciliation engine: Level 1 totals, Level 2 records, Level 3 fields."""
import math
from dataclasses import dataclass, field

import pandas as pd

from ..constants import DOMAIN_SPECS, Domain, ExceptionCategory, Severity
from . import root_cause


@dataclass
class SummaryResult:
    metric: str
    source_value: float
    target_value: float

    @property
    def difference(self) -> float:
        return round(self.target_value - self.source_value, 6)

    def matched(self, tolerance: float = 0.0) -> bool:
        return abs(self.difference) <= tolerance


@dataclass
class RecordOutcome:
    record_key: str
    status: str  # MATCHED | MISMATCHED | MISSING_IN_TARGET | MISSING_IN_SOURCE
    source_data: dict | None
    target_data: dict | None
    field_differences: list[dict] = field(default_factory=list)
    variance: float = 0.0


@dataclass
class ExceptionDraft:
    domain: str
    category: str
    severity: str
    root_cause: str
    root_cause_detail: str
    description: str
    record_key: str | None = None
    field: str | None = None
    source_value: str | None = None
    target_value: str | None = None
    variance: float = 0.0

    @property
    def signature(self) -> tuple:
        return (self.domain, self.category, self.record_key, self.field)


@dataclass
class DomainResult:
    domain: str
    summaries: list[SummaryResult]
    records: list[RecordOutcome]
    exceptions: list[ExceptionDraft]
    source_df: pd.DataFrame
    target_df: pd.DataFrame

    @property
    def total_records(self) -> int:
        return len(self.records)

    @property
    def matched_records(self) -> int:
        return sum(1 for r in self.records if r.status == "MATCHED")

    @property
    def match_pct(self) -> float:
        return 100.0 if not self.records else round(100.0 * self.matched_records / self.total_records, 4)


def _is_null(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _clean(value):
    return None if _is_null(value) else value


def _to_float(value) -> float | None:
    if _is_null(value) or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def values_equal(source_value, target_value, numeric: bool, tolerance: float = 0.0) -> bool:
    if _is_null(source_value) and _is_null(target_value):
        return True
    if _is_null(source_value) or _is_null(target_value):
        return False
    if numeric:
        s, t = _to_float(source_value), _to_float(target_value)
        if s is not None and t is not None:
            return abs(s - t) <= tolerance + 1e-9
    return str(source_value) == str(target_value)


def _frame(rows: list[dict], key: str, columns: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for col in [key, *columns]:
        if col not in df.columns:
            df[col] = None
    if len(df):
        df[key] = df[key].astype(str)
    return df


def _sum(df: pd.DataFrame, col: str, mask=None) -> float:
    if not len(df) or col not in df.columns:
        return 0.0
    series = pd.to_numeric(df[col] if mask is None else df.loc[mask, col], errors="coerce")
    return round(float(series.fillna(0).sum()), 6)


def _count(df: pd.DataFrame, col: str, values: set) -> float:
    if not len(df) or col not in df.columns:
        return 0.0
    return float(df[col].astype(str).str.upper().isin({v.upper() for v in values}).sum())


def level1_summaries(domain: str, src: pd.DataFrame, tgt: pd.DataFrame) -> list[SummaryResult]:
    spec = DOMAIN_SPECS[domain]
    key = spec["key"]
    out = [
        SummaryResult("record_count", float(len(src)), float(len(tgt))),
        SummaryResult("distinct_keys", float(src[key].nunique() if len(src) else 0),
                      float(tgt[key].nunique() if len(tgt) else 0)),
    ]
    for col in spec["numeric"]:
        out.append(SummaryResult(f"sum_{col}", _sum(src, col), _sum(tgt, col)))

    def both(metric, fn):
        out.append(SummaryResult(metric, fn(src), fn(tgt)))

    if domain == Domain.TRANSACTION.value:
        for direction in ("DEBIT", "CREDIT"):
            both(f"{direction.lower()}_count", lambda d, x=direction: _count(d, "direction", {x}))
            both(f"{direction.lower()}_total",
                 lambda d, x=direction: _sum(d, "amount", d["direction"].astype(str).str.upper() == x)
                 if len(d) else 0.0)
        for status in ("POSTED", "PENDING", "REVERSED"):
            both(f"{status.lower()}_count", lambda d, x=status: _count(d, "status", {x}))
    elif domain == Domain.AML.value:
        both("high_risk_cases", lambda d: _count(d, "risk_rating", {"HIGH"}))
        both("sar_filed", lambda d: _count(d, "sar_filed", {"TRUE", "Y", "YES", "1"}))
        both("watchlist_matches", lambda d: _count(d, "watchlist_match", {"TRUE", "Y", "YES", "1"}))
    elif domain == Domain.KYC.value:
        both("pep_customers", lambda d: _count(d, "pep_flag", {"TRUE", "Y", "YES", "1"}))
        both("high_risk_customers", lambda d: _count(d, "risk_classification", {"HIGH"}))
    elif domain == Domain.SANCTIONS.value:
        both("open_matches", lambda d: _count(d, "match_status", {"OPEN"}))
        both("closed_matches", lambda d: _count(d, "match_status", {"CLOSED"}))
    elif domain == Domain.CUSTOMER.value:
        both("active_customers", lambda d: _count(d, "status", {"ACTIVE"}))
    elif domain == Domain.ACCOUNT.value:
        both("active_accounts", lambda d: _count(d, "status", {"ACTIVE"}))
    return out


def _category_for(domain: str, field_name: str) -> str:
    if domain == Domain.BALANCE.value:
        return ExceptionCategory.BALANCE_VARIANCE.value
    if domain == Domain.AML.value:
        return ExceptionCategory.AML_VALIDATION_FAILURE.value
    return ExceptionCategory.MAPPING_ISSUE.value


def _severity_for(category: str, domain: str, field_name: str | None, variance: float,
                  source_row: dict | None, critical_amount: float) -> str:
    if category == ExceptionCategory.BALANCE_VARIANCE.value:
        amount = abs(variance)
        if amount >= critical_amount:
            return Severity.CRITICAL.value
        if amount >= 1000:
            return Severity.HIGH.value
        if amount >= 1:
            return Severity.MEDIUM.value
        return Severity.LOW.value
    if category == ExceptionCategory.MISSING_RECORD.value:
        if domain in {Domain.BALANCE.value, Domain.AML.value, Domain.SANCTIONS.value}:
            return Severity.CRITICAL.value
        return Severity.HIGH.value
    if category == ExceptionCategory.DUPLICATE_RECORD.value:
        return Severity.HIGH.value
    if category == ExceptionCategory.UNEXPECTED_RECORD.value:
        return Severity.MEDIUM.value
    if category == ExceptionCategory.AML_VALIDATION_FAILURE.value:
        high_risk = str((source_row or {}).get("risk_rating", "")).upper() == "HIGH"
        if field_name in {"risk_rating", "risk_score"} and high_risk:
            return Severity.CRITICAL.value
        return Severity.HIGH.value
    if domain == Domain.AUDIT.value:
        return Severity.LOW.value
    if (domain, field_name) in {("kyc", "pep_flag"), ("kyc", "risk_classification"),
                                ("sanctions", "match_status"), ("transaction", "amount")}:
        return Severity.CRITICAL.value
    if domain in {Domain.KYC.value, Domain.SANCTIONS.value}:
        return Severity.HIGH.value
    return Severity.MEDIUM.value


def _fmt(value) -> str | None:
    return None if _is_null(value) else str(value)[:256]


def reconcile_domain(domain: str, source_rows: list[dict], target_rows: list[dict],
                     tolerance: float = 0.0, critical_amount: float = 10000.0) -> DomainResult:
    spec = DOMAIN_SPECS[domain]
    key, fields, numeric = spec["key"], spec["fields"], set(spec["numeric"])
    src, tgt = _frame(source_rows, key, fields), _frame(target_rows, key, fields)

    summaries = level1_summaries(domain, src, tgt)
    exceptions: list[ExceptionDraft] = []

    for side, df in (("target", tgt), ("source", src)):
        if not len(df):
            continue
        dup_keys = df.loc[df[key].duplicated(keep=False), key].value_counts()
        for dup_key, occurrences in dup_keys.items():
            cause, detail = root_cause.classify_duplicate()
            if side == "source":
                cause, detail = ("SOURCE_ISSUE",
                                 "Primary key duplicated in the source extract - source data quality issue.")
            exceptions.append(ExceptionDraft(
                domain=domain, category=ExceptionCategory.DUPLICATE_RECORD.value,
                severity=Severity.HIGH.value, root_cause=cause, root_cause_detail=detail,
                description=f"{key}={dup_key} appears {occurrences} times in {side}.",
                record_key=str(dup_key), field=key,
            ))

    src_u = src.drop_duplicates(subset=[key], keep="first") if len(src) else src
    tgt_u = tgt.drop_duplicates(subset=[key], keep="first") if len(tgt) else tgt
    src_map = {r[key]: r for r in src_u.astype(object).where(src_u.notna(), None).to_dict("records")}
    tgt_map = {r[key]: r for r in tgt_u.astype(object).where(tgt_u.notna(), None).to_dict("records")}

    missing_in_target = [k for k in src_map if k not in tgt_map]
    missing_ratio = len(missing_in_target) / len(src_map) if src_map else 0.0

    records: list[RecordOutcome] = []
    for rec_key in list(src_map) + [k for k in tgt_map if k not in src_map]:
        s_row, t_row = src_map.get(rec_key), tgt_map.get(rec_key)
        if t_row is None:
            cause, detail = root_cause.classify_missing_in_target(missing_ratio)
            category = ExceptionCategory.MISSING_RECORD.value
            records.append(RecordOutcome(rec_key, "MISSING_IN_TARGET", s_row, None))
            exceptions.append(ExceptionDraft(
                domain=domain, category=category,
                severity=_severity_for(category, domain, None, 0, s_row, critical_amount),
                root_cause=cause, root_cause_detail=detail,
                description=f"{key}={rec_key} exists in source but is missing in target.",
                record_key=rec_key,
            ))
            continue
        if s_row is None:
            cause, detail = root_cause.classify_missing_in_source()
            category = ExceptionCategory.UNEXPECTED_RECORD.value
            records.append(RecordOutcome(rec_key, "MISSING_IN_SOURCE", None, t_row))
            exceptions.append(ExceptionDraft(
                domain=domain, category=category,
                severity=_severity_for(category, domain, None, 0, None, critical_amount),
                root_cause=cause, root_cause_detail=detail,
                description=f"{key}={rec_key} exists in target but not in source.",
                record_key=rec_key,
            ))
            continue

        diffs, record_variance = [], 0.0
        for col in fields:
            sv, tv = _clean(s_row.get(col)), _clean(t_row.get(col))
            is_numeric = col in numeric
            if values_equal(sv, tv, is_numeric, tolerance):
                continue
            variance = 0.0
            if is_numeric:
                sf, tf = _to_float(sv), _to_float(tv)
                variance = round((tf or 0.0) - (sf or 0.0), 6)
                record_variance += abs(variance)
            diffs.append({"field": col, "source": sv, "target": tv, "difference": variance})
            cause, detail = root_cause.classify_field_difference(col, sv, tv)
            category = _category_for(domain, col)
            exceptions.append(ExceptionDraft(
                domain=domain, category=category,
                severity=_severity_for(category, domain, col, variance, s_row, critical_amount),
                root_cause=cause, root_cause_detail=detail,
                description=f"{key}={rec_key}: '{col}' source={_fmt(sv)} target={_fmt(tv)}"
                            + (f" (variance {variance:+,.2f})" if is_numeric else ""),
                record_key=rec_key, field=col, source_value=_fmt(sv), target_value=_fmt(tv),
                variance=variance,
            ))
        records.append(RecordOutcome(rec_key, "MISMATCHED" if diffs else "MATCHED", s_row, t_row,
                                     diffs, round(record_variance, 6)))

    return DomainResult(domain, summaries, records, exceptions, src, tgt)
