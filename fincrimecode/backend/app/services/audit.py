from sqlalchemy.orm import Session

from ..models import AuditLog


def log_action(db: Session, actor: str, action: str, entity: str, entity_id: str | int = "",
               detail: dict | None = None) -> None:
    db.add(AuditLog(actor=actor, action=action, entity=entity, entity_id=str(entity_id),
                    detail=detail or {}))
