from app.constants import RootCause
from app.services import root_cause, rules_engine
from app.services.recon_engine import reconcile_domain


def _bal(aid, cur, ledger=None):
    ledger = cur if ledger is None else ledger
    return {"account_id": aid, "current_balance": cur, "available_balance": cur, "ledger_balance": ledger,
            "blocked_balance": 0, "opening_balance": 0, "closing_balance": cur}


def test_level1_level2_level3_balance():
    src = [_bal("A1", 100.0), _bal("A2", 250.0), _bal("A3", 10.0)]
    tgt = [_bal("A1", 100.0), _bal("A2", 25000.0, 250.0), _bal("A4", 5.0), _bal("A4", 5.0)]
    res = reconcile_domain("balance", src, tgt)
    by_metric = {s.metric: s for s in res.summaries}
    assert by_metric["record_count"].source_value == 3 and by_metric["record_count"].target_value == 4
    status = {r.record_key: r.status for r in res.records}
    assert status == {"A1": "MATCHED", "A2": "MISMATCHED", "A3": "MISSING_IN_TARGET", "A4": "MISSING_IN_SOURCE"}
    a2 = next(r for r in res.records if r.record_key == "A2")
    assert {d["field"] for d in a2.field_differences} == {"current_balance", "available_balance", "closing_balance"}
    cats = {e.category for e in res.exceptions}
    assert {"BALANCE_VARIANCE", "MISSING_RECORD", "UNEXPECTED_RECORD", "DUPLICATE_RECORD"} <= cats
    variance = next(e for e in res.exceptions if e.field == "current_balance")
    assert variance.severity == "CRITICAL"
    assert variance.root_cause == RootCause.TRANSFORMATION_ISSUE.value
    assert res.match_pct == 25.0


def test_root_cause_heuristics():
    assert root_cause.classify_field_difference("x", 10.0, -10.0)[0] == "TRANSFORMATION_ISSUE"
    assert root_cause.classify_field_difference("x", 10.0, 10.01)[0] == "TRANSFORMATION_ISSUE"
    assert root_cause.classify_field_difference("x", 10.0, 9000.0)[0] == "DATA_QUALITY_ISSUE"
    assert root_cause.classify_field_difference("status", "ACTIVE", "A")[0] == "MAPPING_ISSUE"
    assert root_cause.classify_field_difference("name", "Ann", "ANN ")[0] == "DATA_QUALITY_ISSUE"
    assert root_cause.classify_field_difference("dob", "1990-02-01", "01/02/1990")[0] == "TRANSFORMATION_ISSUE"
    assert root_cause.classify_field_difference("notes", "abc", None)[0] == "MAPPING_ISSUE"
    assert root_cause.classify_field_difference("notes", None, "x")[0] == "SOURCE_ISSUE"
    assert root_cause.classify_missing_in_target(0.5)[0] == "LOAD_ISSUE"
    assert root_cause.classify_missing_in_target(0.01)[0] == "MISSING_RECORDS"


def test_rules_engine_categories():
    src = [{"case_id": "C1", "customer_id": "X", "risk_rating": "HIGH", "risk_score": 90, "case_status": "OPEN"},
           {"case_id": "C2", "customer_id": "Y", "risk_rating": "LOW", "risk_score": 10, "case_status": "OPEN"}]
    tgt = [{"case_id": "C1", "customer_id": "X", "risk_rating": "MEDIUM", "risk_score": 90, "case_status": "OPEN"},
           {"case_id": "C2", "customer_id": "Y", "risk_rating": "LOW", "risk_score": 10, "case_status": None}]
    res = reconcile_domain("aml", src, tgt)
    count = rules_engine.evaluate("RECONCILIATION", "aml", {"metric": "record_count"}, res)
    assert count.passed
    comp = rules_engine.evaluate("COMPLIANCE", "aml", {"filter_field": "risk_rating", "filter_values": ["HIGH"],
                                                       "required_fields": ["risk_rating"]}, res)
    assert not comp.passed and "C1" in comp.detail
    completeness = rules_engine.evaluate("COMPLETENESS", "aml", {}, res)
    assert not completeness.passed and "case_status=1" in completeness.detail
    pct = rules_engine.evaluate("PERCENTAGE_THRESHOLD", "aml", {"max_mismatch_pct": 60}, res)
    assert not pct.passed  # 100% mismatched

    bal = reconcile_domain("balance", [_bal("A1", 1.0)], [_bal("A1", 1.5)])
    thr = rules_engine.evaluate("THRESHOLD", "balance", {"field": "current_balance", "operator": "<=", "value": 1}, bal)
    assert thr.passed and thr.actual == "0.50"


def test_rule_param_validation():
    import pytest

    with pytest.raises(rules_engine.RuleError):
        rules_engine.validate_params("THRESHOLD", "balance", {"field": "nope"})
    with pytest.raises(rules_engine.RuleError):
        rules_engine.validate_params("THRESHOLD", "balance", {"field": "current_balance", "operator": "__import__"})
