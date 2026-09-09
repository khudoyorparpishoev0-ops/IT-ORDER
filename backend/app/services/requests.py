"""Жизненный цикл заявки на расход.

Переходы статусов — единственное место, где меняется `status`:

    DRAFT ─submit─▶ PENDING ─approve─▶ SOURCING ─priced──▶ PRICED
                       │                   │                 │
                       │                   └─всё со склада──▶ FULFILLED
                       │                                     │
                       └──reject──▶ REJECTED ◀──reject───────┘
                                                    │
                                          PRICED ─approve─▶ APPROVED ─pay─▶ PAID

Сотрудник описывает потребность без цен: цены знает отдел закупа.
Руководитель решает дважды — сначала нужна ли покупка (PENDING), потом
согласен ли он с суммой (PRICED). Между решениями закуп проверяет склад:
что нашлось — закрывает складом, на остальное ставит цены. Нашлось всё —
заявка закрывается как FULFILLED, денег не потребовалось.

Обратных переходов нет: ошибочное решение исправляется новой заявкой,
история неизменяема.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
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
    SourcingIn,
)
from app.services.audit import write_audit

SYSTEM_ACTOR = "СИСТЕМА"

#: Статусы, в которых у заявки есть настоящая сумма и она считается
#: расходом. До оценки закупа суммы нет вовсе, а закрытая складом заявка
#: денег не стоила.
SPENT_STATUSES = (
    RequestStatus.PRICED,
    RequestStatus.APPROVED,
    RequestStatus.PAID,
)


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
        # Строки нужны и списку: наименование заявки складывается из
        # первой строки, отдельного поля «название» у заявки нет намеренно.
        selectinload(ExpenseRequest.lines),
    )


def title_of(request: ExpenseRequest) -> str:
    """Наименование заявки для списка: первая строка сметы.

    Отдельного названия у заявки нет — сотрудник пишет, что нужно, а не
    придумывает заголовок. Если строк несколько, добавляем «и ещё N».
    """
    lines = sorted(request.lines, key=lambda line: line.id)
    if not lines:
        return "Пустой черновик"
    rest = len(lines) - 1
    if rest == 0:
        return lines[0].title
    return f"{lines[0].title} и ещё {rest}"


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
        # Один поиск на всё, что человек помнит о заявке: номер, объект,
        # автор, что просили. Строки ищутся подзапросом, чтобы заявка с
        # тремя совпавшими строками не пришла трижды.
        pattern = f"%{search.strip().lower()}%"
        line_match = (
            select(ExpenseLine.request_id)
            .where(func.lower(ExpenseLine.title).like(pattern))
            .scalar_subquery()
        )
        stmt = stmt.join(ExpenseRequest.employee).join(ExpenseRequest.project)
        count_stmt = count_stmt.join(
            Employee, Employee.id == ExpenseRequest.employee_id
        ).join(Project, Project.id == ExpenseRequest.project_id)
        conditions.append(
            or_(
                func.lower(Employee.full_name).like(pattern),
                func.lower(ExpenseRequest.number).like(pattern),
                func.lower(Project.name).like(pattern),
                ExpenseRequest.id.in_(line_match),
            )
        )

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
def _apply_lines(request: ExpenseRequest, lines: list[ExpenseLineIn]) -> None:
    """Заменяет состав заявки. Цен здесь нет — их проставит закуп."""
    request.lines.clear()
    for line in lines:
        request.lines.append(
            ExpenseLine(
                title=line.title,
                quantity=line.quantity,
                unit=(line.unit or "").strip() or None,
                price=None,
                total=None,
                from_stock=False,
            )
        )
    request.amount = Decimal("0.00")


def recalculate_amount(request: ExpenseRequest) -> Decimal:
    """Сумма заявки — только оценённые строки, которых нет на складе.

    Складские строки денег не стоят и в сумму не входят: иначе бюджет
    показывал бы расход, которого не было.
    """
    total = sum(
        (to_decimal(line.total) for line in request.lines if not line.from_stock and line.total),
        Decimal("0.00"),
    )
    request.amount = to_decimal(total)
    return request.amount


def is_priced(request: ExpenseRequest) -> bool:
    """Прошла ли заявка оценку закупа. До этого сумма ничего не значит."""
    return request.status in (
        RequestStatus.PRICED,
        RequestStatus.APPROVED,
        RequestStatus.PAID,
        RequestStatus.FULFILLED,
    ) or (
        request.status is RequestStatus.REJECTED and request.sourced_at is not None
    )


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
    """Отправляет черновик руководителю — согласовать саму покупку.

    Автоодобрения по сумме здесь нет и быть не может: суммы на этом шаге
    ещё не существует, её узнает закуп.
    """
    if request.status is not RequestStatus.DRAFT:
        raise ConflictError(f"Заявка {request.number} уже подана")
    if not request.lines:
        raise ValidationError("В заявке нет ни одной строки")

    request.status = RequestStatus.PENDING
    request.submitted_at = utcnow()
    _add_event(
        request, EventKind.SUBMITTED, "Заявка отправлена на согласование", actor
    )
    write_audit(session, entity="request", entity_id=request.number, action="submit")
    session.flush()
    return request


def start_sourcing(
    session: Session, request: ExpenseRequest, *, actor: str | None = None
) -> None:
    """Потребность одобрена — заявка уходит в отдел закупа."""
    request.status = RequestStatus.SOURCING
    request.sourcing_started_at = utcnow()
    _add_event(
        request,
        EventKind.SOURCING,
        "Потребность одобрена, заявка передана в отдел закупа",
        actor,
    )
    write_audit(session, entity="request", entity_id=request.number, action="sourcing")


def apply_sourcing(
    session: Session, request_id: int, data: SourcingIn, *, actor: str
) -> ExpenseRequest:
    """Ответ отдела закупа: что нашлось на складе, а что почём купить.

    Заявка возвращается руководителю на утверждение суммы. Если склад
    закрыл всё, покупать нечего — заявка завершается без оплаты.
    """
    request = get_request(session, request_id, full=True)
    if request.status is not RequestStatus.SOURCING:
        raise ConflictError(
            f"Заявка {request.number} не ждёт оценки закупа "
            f"(статус {request.status.value})"
        )

    decisions = {item.id: item for item in data.lines}
    known = {line.id for line in request.lines}
    if decisions.keys() != known:
        raise ValidationError(
            "Ответ закупа должен покрывать все строки заявки, и только их"
        )

    for line in request.lines:
        decision = decisions[line.id]
        line.from_stock = decision.from_stock
        if decision.from_stock:
            # Со склада — денег по строке нет, цену не храним.
            line.price = None
            line.total = None
        else:
            line.price = to_decimal(decision.price)
            line.total = to_decimal(line.price * line.quantity)

    recalculate_amount(request)
    now = utcnow()
    request.sourced_at = now
    request.sourced_by = actor
    request.sourcing_comment = (data.comment or "").strip() or None

    from_stock = [line for line in request.lines if line.from_stock]
    to_buy = [line for line in request.lines if not line.from_stock]

    if from_stock:
        _add_event(
            request,
            EventKind.FULFILLED,
            "Со склада: " + ", ".join(line.title for line in from_stock),
            actor,
        )

    if to_buy:
        request.status = RequestStatus.PRICED
        _add_event(
            request,
            EventKind.PRICED,
            f"Закуп оценил заявку на {somoni(request.amount)}"
            + (f", {len(from_stock)} поз. закрыто складом" if from_stock else ""),
            actor,
        )
        action = "priced"
    else:
        # Покупать нечего: заявка закрыта складом, оплаты не будет.
        request.status = RequestStatus.FULFILLED
        request.decided_at = now
        _add_event(
            request,
            EventKind.FULFILLED,
            "Всё нашлось на складе, покупка не требуется",
            actor,
        )
        action = "fulfilled"

    if request.sourcing_comment:
        _add_event(
            request, EventKind.COMMENTED, f"Закуп: «{request.sourcing_comment}»", actor
        )

    write_audit(
        session,
        entity="request",
        entity_id=request.number,
        action=action,
        username=actor,
        details=somoni(request.amount) if to_buy else "закрыто складом",
    )
    session.flush()
    return request


#: Статусы, в которых заявка ждёт решения руководителя. Их два: сначала
#: согласуется сама покупка, потом — сумма, которую назвал закуп.
DECIDABLE = (RequestStatus.PENDING, RequestStatus.PRICED)


def decide_request(
    session: Session, request_id: int, data: DecisionIn
) -> ExpenseRequest:
    """Решение руководителя.

    Из PENDING одобрение отправляет заявку в закуп, из PRICED — в оплату.
    Отказ на любом шаге закрывает заявку.
    """
    request = get_request(session, request_id, full=True)
    if request.status not in DECIDABLE:
        raise ConflictError(
            f"Заявка {request.number} не ждёт решения (статус {request.status.value})"
        )

    comment = (data.comment or "").strip() or None
    if not data.approve and not comment:
        raise ValidationError("Комментарий обязателен при отклонении заявки")

    deciding_amount = request.status is RequestStatus.PRICED

    if not data.approve:
        request.status = RequestStatus.REJECTED
        request.decided_at = utcnow()
        request.decided_by = data.actor
        request.decision_comment = comment
        _add_event(
            request, EventKind.REJECTED, f"Заявка отклонена: {comment}", data.actor
        )
        write_audit(
            session,
            entity="request",
            entity_id=request.number,
            action="reject",
            username=data.actor,
        )
        session.flush()
        return request

    if deciding_amount:
        request.status = RequestStatus.APPROVED
        request.decided_at = utcnow()
        request.decided_by = data.actor
        request.decision_comment = comment
        _add_event(
            request,
            EventKind.APPROVED,
            f"Сумма утверждена: {somoni(request.amount)}",
            data.actor,
        )
        write_audit(
            session,
            entity="request",
            entity_id=request.number,
            action="approve",
            username=data.actor,
        )
    else:
        # Согласована потребность, не деньги: суммы ещё нет.
        request.decision_comment = comment
        start_sourcing(session, request, actor=data.actor)

    if comment:
        _add_event(request, EventKind.COMMENTED, f"Комментарий: «{comment}»", data.actor)

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


#: У кого лежит заявка на каждом шаге: (кто, что он с ней делает).
#: Ключ используется и на фронтенде, поэтому строкой, а не enum-ом.
AWAITING: dict[RequestStatus, tuple[str, str]] = {
    RequestStatus.DRAFT: ("author", "Черновик у автора"),
    RequestStatus.PENDING: ("manager", "У руководителя: согласовать покупку"),
    RequestStatus.SOURCING: ("procurement", "У отдела закупа: склад и цены"),
    RequestStatus.PRICED: ("manager", "У руководителя: утвердить сумму"),
    RequestStatus.APPROVED: ("finance", "В бухгалтерии: ждёт выплаты"),
    RequestStatus.PAID: ("closed", "Выплачена"),
    RequestStatus.FULFILLED: ("closed", "Закрыта складом"),
    RequestStatus.REJECTED: ("closed", "Отклонена"),
}


def awaiting_stage(request: ExpenseRequest) -> str:
    """Кто сейчас держит заявку: author / manager / procurement / finance /
    closed."""
    return AWAITING[request.status][0]


def awaiting_label(request: ExpenseRequest) -> str:
    return AWAITING[request.status][1]


def awaiting_since(request: ExpenseRequest) -> datetime | None:
    """С какого момента заявка ждёт именно текущего шага.

    Не с подачи: иначе «лежит 5 дней» относилось бы к пути целиком, и
    было бы непонятно, кто именно задерживает.
    """
    if request.status is RequestStatus.DRAFT:
        return request.created_at
    if request.status is RequestStatus.PENDING:
        return request.submitted_at
    if request.status is RequestStatus.SOURCING:
        return request.sourcing_started_at
    if request.status is RequestStatus.PRICED:
        return request.sourced_at
    if request.status is RequestStatus.APPROVED:
        return request.decided_at
    return None


def awaiting_days(request: ExpenseRequest, *, now: datetime | None = None) -> int | None:
    """Сколько полных суток заявка лежит на текущем шаге."""
    since = awaiting_since(request)
    if since is None:
        return None
    reference = now or utcnow()
    return max(0, (to_local(reference).date() - to_local(since).date()).days)


def awaiting_people(session: Session, request: ExpenseRequest) -> list[str]:
    """Кто может сделать следующий шаг именно сейчас.

    Персональных назначений в системе нет: заявку берёт любой, у кого есть
    право. Показываем поимённо — иначе «у руководителя» ничего не говорит
    о том, кого торопить.
    """
    from app.core.permissions import Permission, has_permission

    stage = awaiting_stage(request)
    if stage == "closed":
        return []
    if stage == "author":
        return [request.employee.full_name] if request.employee else []

    permission = {
        "manager": Permission.DECIDE_REQUEST,
        "procurement": Permission.SOURCE_REQUEST,
        "finance": Permission.PAY_REQUEST,
    }[stage]

    people = session.scalars(
        select(Employee).where(Employee.active.is_(True)).order_by(Employee.full_name)
    )
    return [
        person.full_name
        for person in people
        if has_permission(person.role, permission)
        # Свою заявку человек не согласует, не оценивает и не оплачивает —
        # значит, и ждать её он не может.
        and person.id != request.employee_id
    ]


def pending_age_days(request: ExpenseRequest, *, now: datetime | None = None) -> int:
    """Сколько полных суток заявка ждёт решения."""
    started = request.submitted_at or request.created_at
    reference = now or utcnow()
    return max(0, (to_local(reference).date() - to_local(started).date()).days)
