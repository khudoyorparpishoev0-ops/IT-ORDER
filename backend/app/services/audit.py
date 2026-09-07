"""Журнал изменений. Пишется при любой правке справочника или заявки."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def write_audit(
    session: Session,
    *,
    entity: str,
    entity_id: str | int,
    action: str,
    username: str | None = None,
    details: str | None = None,
) -> None:
    """Добавляет строку в audit_log. Commit делает вызывающий слой."""
    session.add(
        AuditLog(
            entity=entity,
            entity_id=str(entity_id),
            action=action,
            username=username,
            details=details,
        )
    )
