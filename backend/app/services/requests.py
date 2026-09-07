"""Жизненный цикл заявки на расход.

Переходы статусов — единственное место, где меняется `status`:

    DRAFT ──submit──▶ PENDING ──approve──▶ APPROVED ──pay──▶ PAID
                         │
                         └──reject──▶ REJECTED

Заявка на сумму не выше порога автоодобрения проходит из DRAFT сразу
в APPROVED. Обратных переходов нет: ошибочное решение исправляется
новой заявкой, история неизменяема.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.money import somoni, to_decimal
from app.core.time import (
    format_local_date,
    format_local_datetime,
    month_bounds,
    to_local,
    utcnow,
)
from app.db.models import (
    REQUEST_NUMBER_SEQ,
    Employee,
    EventKind,
    ExpenseLine,
    ExpenseRequest,
    Payment,
    Project,
    RequestEvent,
    RequestStatus,
)
from app.schemas.request import (
    DecisionIn,
    ExpenseLineIn,
    PaymentIn,
    RequestCreate,
    RequestUpdate,
)
from app.services.audit import write_audit

SYSTEM_ACTOR = "СИСТЕМА"

#: Статусы, в которых заявка уже потрачена из лимита сотрудника.
SPENT_STATUSES = (RequestStatus.PENDING, RequestStatus.APPROVED, RequestStatus.PAID)


# --------------------------------------------------------------------------
# Номера заявок
# --------------------------------------------------------------------------
def next_number(session: Session) -> str:
    """Следующий номер вида «РЗ-0001».

    Значение берётся из последовательности базы, а не из max(number):
    последовательность не откатывается, поэтому удалённый черновик не
    возвращает свой номер в оборот. Пропуск в нумерации безобиден,
    а два документа с одним номером — нет.
    """
    prefix = get_settings().request_number_prefix
    value = session.scalar(REQUEST_NUMBER_SEQ.next_value())
    return f"{prefix}-{value:04d}"


# --------------------------------------------------------------------------
# Чтение
# --------------------------------------------------------------------------
def _base_query() -> Select[tuple[ExpenseRequest]]:
    return select(ExpenseRequest).options(
        selectinload(ExpenseRequest.employee),
        selectinload(ExpenseRequest.project),
    )


def get_request(session: Session, request_id: int, *, full: bool = False) -> ExpenseRequest:
    stmt = _base_query().where(ExpenseRequest.id == request_id)
    if full:
        stmt = stmt.options(
            selectinload(ExpenseRequest.lines),
            selectinload(ExpenseRequest.events),
            selectinload(ExpenseRequest.payment),
        )
    request = session.scalar(stmt)
    if request is None:
        raise NotFoundError(f"Заявка {request_id} не найдена")
    return request


def get_by_number(session: Session, number: str) -> ExpenseRequest:
    request = session.scalar(_base_query().where(ExpenseRequest.number == number))
    if request is None:
        raise NotFoundError(f"Заявка {number} не найдена")
    return request


def list_requests(
    session: Session,
    *,
    status: RequestStatus | None = None,
    employee_id: int | None = None,
    project_id: int | None = None,
    year: int | None = None,
    month: int | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ExpenseRequest], int]:
    """Список заявок с фильтрами. Возвращает страницу и общее число записей."""
    stmt = _base_query()
    count_stmt = select(func.count()).select_from(ExpenseRequest)

    conditions = []
    if status is not None:
        conditions.append(ExpenseRequest.status == status)
    if employee_id is not None:
        conditions.append(ExpenseRequest.employee_id == employee_id)
    if project_id is not None:
        conditions.append(ExpenseRequest.project_id == project_id)
    if year is not None and month is not None:
        start, end = month_bounds(year, month)
        conditions.append(ExpenseRequest.created_at >= start)
        conditions.append(ExpenseRequest.created_at < end)
    if search:
        pattern = f"%{search.strip().lower()}%"
        stmt = stmt.join(ExpenseRequest.employee)
        count_stmt = count_stmt.join(Employee, Employee.id == ExpenseRequest.employee_id)
        conditions.append(func.lower(Employee.full_name).like(pattern))

    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)

    total = session.scalar(count_stmt) or 0
    stmt = stmt.order_by(ExpenseRequest.created_at.desc()).limit(limit).offset(offset)
    return list(session.scalars(stmt)), total


def spent_by_employee(
    session: Session, employee_id: int, *, year: int, month: int
) -> Decimal:
    """Сколько сотрудник израсходовал за месяц.

    Считаем поданные, одобренные и оплаченные заявки: черновик ещё не
    обязательство, отклонённая заявка лимит не расходует.
    """
    start, end = month_bounds(year, month)
    total = session.scalar(
        select(func.coalesce(func.sum(ExpenseRequest.amount), 0)).where(
            ExpenseRequest.employee_id == employee_id,
            ExpenseRequest.status.in_(SPENT_STATUSES),
            ExpenseRequest.created_at >= start,
            ExpenseRequest.created_at < end,
        )
    )
    return to_decimal(total or 0)


# --------------------------------------------------------------------------
# Запись
# --------------------------------------------------------------------------
def _line_total(line: ExpenseLineIn) -> Decimal:
    return to_decimal(to_decimal(line.price) * line.quantity)


def _apply_lines(request: ExpenseRequest, lines: list[ExpenseLineIn]) -> None:
    """Заменяет состав заявки и пересчитывает итог."""
    request.lines.clear()
    total = Decimal("0.00")
    for line in lines:
        line_total = _line_total(line)
        total += line_total
        request.lines.append(
            ExpenseLine(
                title=line.title,
                quantity=line.quantity,
                price=to_decimal(line.price),
                total=line_total,
            )
        )
    request.amount = to_decimal(total)


def _add_event(
    request: ExpenseRequest, kind: EventKind, text: str, actor: str | None = None
) -> None:
    request.events.append(
        RequestEvent(kind=kind, text=text, actor=(actor or SYSTEM_ACTOR).upper())
    )


def create_request(session: Session, data: RequestCreate) -> ExpenseRequest:
    employee = session.get(Employee, data.employee_id)
    if employee is None:
        raise NotFoundError(f"Сотрудник {data.employee_id} не найден")
    if not employee.active:
        raise ValidationError(f"Сотрудник {employee.full_name} отключён")

    project = session.get(Project, data.project_id)
    if project is None:
        raise NotFoundError(f"Объект {data.project_id} не найден")
    if not project.active:
        raise ValidationError(f"Объект «{project.name}» отключён")

    request = ExpenseRequest(
        number=next_number(session),
        employee_id=employee.id,
        project_id=project.id,
        status=RequestStatus.DRAFT,
    )
    _apply_lines(request, data.lines)
    _add_event(request, EventKind.CREATED, "Заявка создана", employee.full_name)
    session.add(request)
    session.flush()

    write_audit(session, entity="request", entity_id=request.number, action="create")

    if data.submit:
        submit_request(session, request, actor=employee.full_name)
    return request


def update_request(
    session: Session, request_id: int, data: RequestUpdate
) -> ExpenseRequest:
    """Правка возможна только у черновика: поданная заявка неизменяема."""
    request = get_request(session, request_id, full=True)
    if request.status is not RequestStatus.DRAFT:
        raise ConflictError(
            f"Заявка {request.number} уже подана, её состав менять нельзя"
        )

    if data.project_id is not None:
        project = session.get(Project, data.project_id)
        if project is None:
            raise NotFoundError(f"Объект {data.project_id} не найден")
        # Та же проверка, что при создании: на отключённый объект заявку
        # не подать ни новой, ни правкой черновика.
        if not project.active:
            raise ValidationError(f"Объект «{project.name}» отключён")
        request.project_id = project.id
    if data.lines is not None:
        _apply_lines(request, data.lines)

    write_audit(session, entity="request", entity_id=request.number, action="update")
    return request


def submit_request(
    session: Session, request: ExpenseRequest, *, actor: str | None = None
) -> ExpenseRequest:
    """Отправляет черновик на согласование.

    Сумма не выше порога автоодобрения закрывается без участия руководителя.
    """
    if request.status is not RequestStatus.DRAFT:
        raise ConflictError(f"Заявка {request.number} уже подана")
    if not request.lines:
        raise ValidationError("В заявке нет ни одной строки расхода")

    now = utcnow()
    request.status = RequestStatus.PENDING
    request.submitted_at = now
    _add_event(request, EventKind.SUBMITTED, "Заявка отправлена на утверждение", actor)

    threshold = to_decimal(get_settings().auto_approve_threshold)
    if request.amount <= threshold:
        request.status = RequestStatus.APPROVED
        request.decided_at = now
        request.decided_by = SYSTEM_ACTOR
        _add_event(
            request,
            EventKind.AUTO_APPROVED,
            f"Одобрено автоматически: сумма не превышает порог {somoni(threshold)}",
        )
        write_audit(
            session, entity="request", entity_id=request.number, action="auto_approve"
        )
    else:
        write_audit(session, entity="request", entity_id=request.number, action="submit")

    session.flush()
    return request


def decide_request(
    session: Session, request_id: int, data: DecisionIn
) -> ExpenseRequest:
    """Решение руководителя: одобрить или отклонить."""
    request = get_request(session, request_id, full=True)
    if request.status is not RequestStatus.PENDING:
        raise ConflictError(
            f"Заявка {request.number} не ждёт решения (статус {request.status.value})"
        )

    comment = (data.comment or "").strip() or None
    if not data.approve and not comment:
        raise ValidationError("Комментарий обязателен при отклонении заявки")

    request.status = RequestStatus.APPROVED if data.approve else RequestStatus.REJECTED
    request.decided_at = utcnow()
    request.decided_by = data.actor
    request.decision_comment = comment

    if data.approve:
        _add_event(
            request, EventKind.APPROVED, f"Заявка одобрена на {somoni(request.amount)}", data.actor
        )
    else:
        _add_event(request, EventKind.REJECTED, f"Заявка отклонена: {comment}", data.actor)
    if comment and data.approve:
        _add_event(request, EventKind.COMMENTED, f"Комментарий: «{comment}»", data.actor)

    write_audit(
        session,
        entity="request",
        entity_id=request.number,
        action="approve" if data.approve else "reject",
        username=data.actor,
    )
    session.flush()
    return request


def pay_request(session: Session, request_id: int, data: PaymentIn) -> ExpenseRequest:
    """Проводит выплату по одобренной заявке."""
    request = get_request(session, request_id, full=True)
    if request.status is not RequestStatus.APPROVED:
        raise ConflictError(
            f"Оплатить можно только одобренную заявку, у {request.number} "
            f"статус {request.status.value}"
        )
    if request.payment is not None:
        raise ConflictError(f"По заявке {request.number} уже есть выплата")

    paid_at = data.paid_at or utcnow()
    if paid_at.tzinfo is None:
        raise ValidationError("paid_at должен быть с таймзоной")
    # Дата из будущего перекашивает реестр выплат и все сводки: месяц
    # закрыт, а платёж «случится» в следующем году. Небольшой запас —
    # на расхождение часов клиента и сервера.
    if paid_at > utcnow() + timedelta(minutes=5):
        raise ValidationError("Дата выплаты не может быть в будущем")
    if request.decided_at is not None and paid_at < request.decided_at:
        raise ValidationError(
            "Дата выплаты раньше решения по заявке — проверьте, что вводите"
        )

    request.payment = Payment(
        amount=request.amount,
        method=data.method,
        document=data.document,
        paid_at=paid_at,
    )
    request.status = RequestStatus.PAID
    request.paid_at = paid_at
    _add_event(
        request,
        EventKind.PAID,
        f"Выплачено {somoni(request.amount)}, документ {data.document}",
        data.actor or "ФИНАНСЫ",
    )
    write_audit(
        session,
        entity="request",
        entity_id=request.number,
        action="pay",
        username=data.actor,
        details=data.document,
    )
    session.flush()
    return request


def delete_request(session: Session, request_id: int) -> None:
    """Удалить можно только черновик: поданные заявки — часть истории."""
    request = get_request(session, request_id)
    if request.status is not RequestStatus.DRAFT:
        raise ConflictError(
            f"Заявка {request.number} уже подана и не может быть удалена"
        )
    number = request.number
    session.delete(request)
    write_audit(session, entity="request", entity_id=number, action="delete")


# --------------------------------------------------------------------------
# Представление
# --------------------------------------------------------------------------
def display_date(request: ExpenseRequest) -> str:
    """Дата для интерфейса: подача, а у черновика — создание."""
    return format_local_date(request.submitted_at or request.created_at)


def event_meta(event: RequestEvent) -> str:
    """«ИВАН ПЕТРОВ · 04.09.2026, 18:12»."""
    return f"{event.actor} · {format_local_datetime(event.created_at)}"


def pending_age_days(request: ExpenseRequest, *, now: datetime | None = None) -> int:
    """Сколько полных суток заявка ждёт решения."""
    started = request.submitted_at or request.created_at
    reference = now or utcnow()
    return max(0, (to_local(reference).date() - to_local(started).date()).days)
