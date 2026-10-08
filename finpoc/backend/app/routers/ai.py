from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import AskRequest
from ..security import require
from ..services import ai
from ..services.audit import log_action

router = APIRouter(prefix="/api/ai", tags=["ai"])

SUGGESTIONS = [
    "Why did reconciliation fail?",
    "Show accounts with highest mismatch.",
    "Which AML cases failed migration?",
    "Show root cause of balance variance.",
    "Show all AML cases with reconciliation failures",
    "Which sanctions matches have issues?",
    "Summarise KYC exceptions",
]


@router.get("/status")
def status(_: User = Depends(require("ai:use"))):
    return {"provider": ai.provider_name(), "suggestions": SUGGESTIONS}


@router.post("/ask")
def ask(body: AskRequest, db: Session = Depends(get_db), user: User = Depends(require("ai:use"))):
    result = ai.ask(db, body.question, body.run_id, body.environment)
    log_action(db, user.username, "AI_QUERY", "ai", "", {"question": body.question, "intent": result["intent"]})
    db.commit()
    return result
