from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import RuleCategory, Severity
from ..db import get_db
from ..models import Rule, User
from ..schemas import RuleIn, RuleOut
from ..security import require
from ..services.audit import log_action
from ..services.rules_engine import RuleError, validate_params

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _validate(body: RuleIn) -> None:
    if body.category not in {c.value for c in RuleCategory}:
        raise HTTPException(400, f"category must be one of {[c.value for c in RuleCategory]}")
    if body.severity not in {s.value for s in Severity}:
        raise HTTPException(400, f"severity must be one of {[s.value for s in Severity]}")
    try:
        validate_params(body.category, body.domain, body.params)
    except (RuleError, TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db), _: User = Depends(require("runs:read"))):
    return list(db.scalars(select(Rule).order_by(Rule.domain, Rule.category, Rule.id)))


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(body: RuleIn, db: Session = Depends(get_db), user: User = Depends(require("rules:write"))):
    _validate(body)
    rule = Rule(**body.model_dump())
    db.add(rule)
    db.flush()
    log_action(db, user.username, "RULE_CREATED", "rule", rule.id, body.model_dump())
    db.commit()
    return rule


@router.put("/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, body: RuleIn, db: Session = Depends(get_db),
                user: User = Depends(require("rules:write"))):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    _validate(body)
    for k, v in body.model_dump().items():
        setattr(rule, k, v)
    log_action(db, user.username, "RULE_UPDATED", "rule", rule_id, body.model_dump())
    db.commit()
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(require("rules:write"))):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    db.delete(rule)
    log_action(db, user.username, "RULE_DELETED", "rule", rule_id, {"name": rule.name})
    db.commit()
