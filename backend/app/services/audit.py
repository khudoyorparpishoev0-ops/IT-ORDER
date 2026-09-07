"""Журнал действий: кто, что, когда и с какого адреса.

Пишется при любой правке справочника и заявки, при входе, выходе и всём,
что касается доступа. Строки только добавляются — журнал не редактируется
и не чистится: иначе он перестаёт быть доказательством.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.audit_context import current_actor, current_ip
from app.db.models import AuditLog, Employee


def write_audit(
    session: Session,
    *,
    entity: str,
    entity_id: str | int,
    action: str,
    username: str | None = None,
    details: str | None = None,
    employee: Employee | None = None,
    ip: str | None = None,
) -> None:
    """Добавляет строку в audit_log. Commit делает вызывающий слой.

    Имя, id сотрудника и адрес берутся из контекста запроса, если их не
    передали явно: у входа и выхода действующий сотрудник ещё (или уже)
    не тот, что в сессии, — там их передают руками.
    """
    actor = current_actor()
    employee_id = employee.id if employee is not None else (actor.id if actor else None)
    if username is None:
        username = employee.full_name if employee is not None else (actor.name if actor else None)

    session.add(
        AuditLog(
            entity=entity,
            entity_id=str(entity_id),
            action=action,
            username=username,
            employee_id=employee_id,
            details=details,
            ip=ip if ip is not None else current_ip(),
        )
    )


def _filtered(
    *,
    entity: str | None,
    action: str | None,
    employee_id: int | None,
    search: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> Select:
    stmt = select(AuditLog)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if employee_id is not None:
        stmt = stmt.where(AuditLog.employee_id == employee_id)
    if date_from is not None:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to is not None:
        # Верхняя граница исключающая: сюда передают начало следующих суток.
        stmt = stmt.where(AuditLog.created_at < date_to)
    if search:
        # Поиск по тому, что видно в таблице: имя, номер объекта записи,
        # пояснение и адрес. ILIKE, потому что регистр вводят как придётся.
        needle = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                AuditLog.username.ilike(needle),
                AuditLog.entity_id.ilike(needle),
                AuditLog.details.ilike(needle),
                AuditLog.ip.ilike(needle),
            )
        )
    return stmt


def list_audit(
    session: Session,
    *,
    entity: str | None = None,
    action: str | None = None,
    employee_id: int | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    """Страница журнала и общее число записей по фильтру.

    Сортировка от новых к старым: журнал читают сверху, «что было только что».
    """
    stmt = _filtered(
        entity=entity,
        action=action,
        employee_id=employee_id,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        session.scalars(
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return rows, total


def audit_actors(session: Session) -> list[tuple[int | None, str]]:
    """Кто вообще встречается в журнале — для выпадающего списка фильтра."""
    rows = session.execute(
        select(AuditLog.employee_id, AuditLog.username)
        .where(AuditLog.username.is_not(None))
        .distinct()
        .order_by(AuditLog.username)
    ).all()
    seen: dict[str, int | None] = {}
    for employee_id, username in rows:
        seen.setdefault(username, employee_id)
    return [(employee_id, username) for username, employee_id in seen.items()]
