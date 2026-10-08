"""Heuristic root-cause classifier used for every exception.

The AI service can enrich these explanations with an LLM, but classification is
deterministic so results are reproducible and auditable.
"""
from datetime import datetime

from ..constants import RootCause

_SCALE_FACTORS = (10.0, 100.0, 1000.0, 0.1, 0.01, 0.001)
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S",
                 "%Y-%m-%d %H:%M:%S")


def _parse_date(value: str) -> datetime | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _to_float(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_missing_in_target(missing_ratio: float) -> tuple[str, str]:
    if missing_ratio >= 0.05:
        return (RootCause.LOAD_ISSUE.value,
                f"{missing_ratio:.1%} of source records absent in target - indicates a failed or "
                "partial load batch.")
    return (RootCause.MISSING_RECORDS.value,
            "Record present in source but not migrated - likely filtered out by an extraction "
            "or transformation rule.")


def classify_missing_in_source() -> tuple[str, str]:
    return (RootCause.LOAD_ISSUE.value,
            "Record exists in target but not in source - possible duplicate load, test data or "
            "late-arriving source record.")


def classify_duplicate() -> tuple[str, str]:
    return (RootCause.LOAD_ISSUE.value,
            "Primary key loaded more than once - load batch was likely re-run without "
            "idempotency checks.")


def classify_field_difference(field: str, source_value, target_value) -> tuple[str, str]:
    if source_value is None and target_value is not None:
        return (RootCause.SOURCE_ISSUE.value,
                f"Source '{field}' is null but target holds '{target_value}' - source data gap "
                "back-filled with a default during migration.")
    if target_value is None:
        return (RootCause.MAPPING_ISSUE.value,
                f"Target '{field}' is null while source holds '{source_value}' - field is not "
                "mapped or was dropped by the transformation.")

    src_num, tgt_num = _to_float(source_value), _to_float(target_value)
    if src_num is not None and tgt_num is not None:
        if src_num != 0 and tgt_num == -src_num:
            return (RootCause.TRANSFORMATION_ISSUE.value,
                    f"Sign inverted on '{field}' - debit/credit sign convention differs between "
                    "source and target.")
        if src_num != 0 and tgt_num != 0:
            ratio = tgt_num / src_num
            for factor in _SCALE_FACTORS:
                if abs(ratio - factor) < 1e-9 * max(1.0, factor):
                    return (RootCause.TRANSFORMATION_ISSUE.value,
                            f"Target '{field}' is {factor:g}x source - unit/decimal scaling error "
                            "(e.g. minor vs major currency units).")
        if abs(tgt_num - src_num) < 1:
            return (RootCause.TRANSFORMATION_ISSUE.value,
                    f"Difference of {tgt_num - src_num:+.4f} on '{field}' - rounding/precision "
                    "loss in transformation.")
        return (RootCause.DATA_QUALITY_ISSUE.value,
                f"Unexplained variance of {tgt_num - src_num:+,.2f} on '{field}' - requires "
                "investigation of source postings after extraction cut-off.")

    src_str, tgt_str = str(source_value), str(target_value)
    if src_str.strip().lower() == tgt_str.strip().lower():
        return (RootCause.DATA_QUALITY_ISSUE.value,
                f"'{field}' differs only by case/whitespace - data cleansing inconsistency.")
    src_date, tgt_date = _parse_date(src_str), _parse_date(tgt_str)
    if src_date and tgt_date and src_date.date() == tgt_date.date():
        return (RootCause.TRANSFORMATION_ISSUE.value,
                f"'{field}' holds the same date in a different format - date transformation issue.")
    short, long_ = sorted((src_str, tgt_str), key=len)
    if 0 < len(short) <= 3 and long_.upper().startswith(short.upper()):
        return (RootCause.MAPPING_ISSUE.value,
                f"'{field}' code '{short}' not translated to '{long_}' - reference data mapping gap.")
    return (RootCause.MAPPING_ISSUE.value,
            f"'{field}' value '{src_str}' migrated as '{tgt_str}' - mapping rule mismatch.")
