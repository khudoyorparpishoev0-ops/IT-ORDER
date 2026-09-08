"""Жизненный цикл заявки: путь через закуп, суммы, переходы статусов.

    DRAFT → PENDING → SOURCING → PRICED → APPROVED → PAID
                                     └→ FULFILLED (всё нашлось на складе)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import ConflictError, ValidationError
from app.db.models import EventKind, PaymentMethod, RequestStatus
from app.schemas.request import (
    DecisionIn,
    ExpenseLineIn,
    PaymentIn,
    RequestCreate,
    RequestUpdate,
    SourcingIn,
    SourcingLineIn,
)
from app.services import requests as svc

MANAGER = "Артём Ковалёв"
BUYER = "Ольга Кузнецова"


def make(employee, project, lines, submit=True) -> RequestCreate:
    return RequestCreate(
        employee_id=employee.id,
        project_id=project.id,
        lines=[ExpenseLineIn(**line) for line in lines],
        submit=submit,
    )


BIG = [
    {"title": "Грунтовка", "quantity": 2, "unit": "канистра"},
    {"title": "Шпатель", "quantity": 1, "unit": "шт."},
    {"title": "Мешки для мусора", "quantity": 5},
]
PRICES = {"Грунтовка": "150.00", "Шпатель": "80.00", "Мешки для мусора": "40.00"}


def sourcing(request, prices: dict[str, str]) -> SourcingIn:
    """Ответ закупа: строка без цены считается найденной на складе."""
    return SourcingIn(
        lines=[
            SourcingLineIn(
                id=line.id,
                from_stock=line.title not in prices,
                price=prices.get(line.title),
            )
            for line in request.lines
        ]
    )


# --------------------------------------------------------------------------
# Подача: сотрудник описывает потребность, цен у него нет
# --------------------------------------------------------------------------
def test_new_request_has_no_amount(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    assert request.status is RequestStatus.PENDING
    assert request.amount == Decimal("0.00")
    assert all(line.price is None and line.total is None for line in request.lines)
    assert svc.is_priced(request) is False


def test_units_are_kept_as_written(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    assert [line.unit for line in request.lines] == ["канистра", "шт.", None]


def test_draft_is_not_submitted(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG, submit=False))
    assert request.status is RequestStatus.DRAFT
    assert request.submitted_at is None


# --------------------------------------------------------------------------
# Первое решение: нужна ли покупка
# --------------------------------------------------------------------------
def test_approval_sends_request_to_procurement(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    svc.decide_request(session, request.id, DecisionIn(approve=True, actor=MANAGER))
    session.refresh(request)

    assert request.status is RequestStatus.SOURCING
    # Решения по деньгам ещё не было: сумма не утверждена.
    assert request.decided_at is None
    assert EventKind.SOURCING in [e.kind for e in request.events]


def test_reject_before_sourcing_closes_request(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    svc.decide_request(
        session,
        request.id,
        DecisionIn(approve=False, comment="Есть в другом отделе", actor=MANAGER),
    )
    session.refresh(request)
    assert request.status is RequestStatus.REJECTED
    assert "другом отделе" in (request.decision_comment or "")


def test_reject_requires_comment(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    with pytest.raises(ValueError):
        DecisionIn(approve=False, comment="   ")
    with pytest.raises(ValidationError):
        svc.decide_request(
            session, request.id, DecisionIn.model_construct(approve=False, comment=None)
        )


# --------------------------------------------------------------------------
# Закуп: склад и цены
# --------------------------------------------------------------------------
def test_sourcing_prices_the_request(session, employee, project, advance) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    advance(request, to="priced", prices=PRICES)
    session.refresh(request)

    assert request.status is RequestStatus.PRICED
    # 2×150 + 1×80 + 5×40 = 580
    assert request.amount == Decimal("580.00")
    assert request.sourced_by == BUYER
    assert request.sourced_at is not None
    assert svc.is_priced(request) is True


def test_stock_lines_cost_nothing(session, employee, project, advance) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    advance(request, to="priced", prices={"Грунтовка": "150.00"})
    session.refresh(request)

    assert request.amount == Decimal("300.00")
    stock = [line for line in request.lines if line.from_stock]
    assert len(stock) == 2
    assert all(line.price is None and line.total is None for line in stock)


def test_everything_from_stock_closes_without_payment(
    session, employee, project, advance
) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    advance(request, to="fulfilled", prices={})
    session.refresh(request)

    assert request.status is RequestStatus.FULFILLED
    assert request.amount == Decimal("0.00")
    assert EventKind.FULFILLED in [e.kind for e in request.events]


def test_fulfilled_request_is_not_paid(session, employee, project, advance) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    advance(request, to="fulfilled", prices={})
    with pytest.raises(ConflictError):
        svc.pay_request(
            session, request.id, PaymentIn(method=PaymentMethod.CASH, document="РКО-1")
        )


def test_sourcing_needs_every_line(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    svc.decide_request(session, request.id, DecisionIn(approve=True, actor=MANAGER))
    partial = SourcingIn(
        lines=[SourcingLineIn(id=request.lines[0].id, price="100.00")]
    )
    with pytest.raises(ValidationError):
        svc.apply_sourcing(session, request.id, partial, actor=BUYER)


def test_price_required_unless_from_stock(session, employee, project) -> None:
    """Строка без цены и без отметки о складе — недосказанность."""
    with pytest.raises(ValueError):
        SourcingLineIn(id=1, from_stock=False, price=None)


def test_sourcing_only_after_approval(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    with pytest.raises(ConflictError):
        svc.apply_sourcing(session, request.id, sourcing(request, PRICES), actor=BUYER)


def test_sourcing_only_once(session, employee, project, advance) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    advance(request, to="priced", prices=PRICES)
    with pytest.raises(ConflictError):
        svc.apply_sourcing(session, request.id, sourcing(request, PRICES), actor=BUYER)


# --------------------------------------------------------------------------
# Второе решение: согласие с суммой
# --------------------------------------------------------------------------
def test_amount_approval_opens_payment(session, employee, project, advance) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    advance(request, to="approved", prices=PRICES)
    session.refresh(request)

    assert request.status is RequestStatus.APPROVED
    assert request.decided_by == MANAGER
    assert request.decided_at is not None


def test_amount_can_be_rejected(session, employee, project, advance) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    advance(request, to="priced", prices=PRICES)
    svc.decide_request(
        session,
        request.id,
        DecisionIn(approve=False, comment="Дорого, ищите дешевле", actor=MANAGER),
    )
    session.refresh(request)
    assert request.status is RequestStatus.REJECTED
    # Заявка была оценена — сумма в ней настоящая, её видно в отчётах.
    assert svc.is_priced(request) is True


def test_no_auto_approval_by_amount(session, employee, project, advance) -> None:
    """Дешёвая заявка тоже ждёт руководителя: порогов больше нет."""
    request = svc.create_request(
        session, make(employee, project, [{"title": "Скотч", "quantity": 1}])
    )
    advance(request, to="priced", prices={"Скотч": "12.00"})
    session.refresh(request)
    assert request.status is RequestStatus.PRICED


def test_decision_only_once(session, employee, project, advance) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    advance(request, to="approved", prices=PRICES)
    with pytest.raises(ConflictError):
        svc.decide_request(session, request.id, DecisionIn(approve=True, actor=MANAGER))


# --------------------------------------------------------------------------
# Оплата
# --------------------------------------------------------------------------
def test_payment_requires_approved_amount(session, employee, project, advance) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    payment = PaymentIn(method=PaymentMethod.CARD, document="ПП-0412")

    with pytest.raises(ConflictError):
        svc.pay_request(session, request.id, payment)

    advance(request, to="priced", prices=PRICES)
    with pytest.raises(ConflictError):
        svc.pay_request(session, request.id, payment)

    svc.decide_request(session, request.id, DecisionIn(approve=True, actor=MANAGER))
    svc.pay_request(session, request.id, payment)
    session.refresh(request)
    assert request.status is RequestStatus.PAID
    assert request.payment is not None
    assert request.payment.amount == request.amount


def test_payment_only_once(session, employee, project, advance) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    advance(request, to="approved", prices=PRICES)
    payment = PaymentIn(method=PaymentMethod.CASH, document="РКО-118")
    svc.pay_request(session, request.id, payment)
    with pytest.raises(ConflictError):
        svc.pay_request(session, request.id, payment)


# --------------------------------------------------------------------------
# Правки, номера, лимиты
# --------------------------------------------------------------------------
def test_submitted_request_cannot_be_edited(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    with pytest.raises(ConflictError):
        svc.update_request(
            session,
            request.id,
            RequestUpdate(lines=[ExpenseLineIn(title="Другое", quantity=1)]),
        )


def test_draft_can_be_edited(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG, submit=False))
    svc.update_request(
        session,
        request.id,
        RequestUpdate(lines=[ExpenseLineIn(title="Только скотч", quantity=3, unit="шт.")]),
    )
    assert len(request.lines) == 1
    assert request.lines[0].unit == "шт."
    assert request.amount == Decimal("0.00")


def test_only_draft_can_be_deleted(session, employee, project) -> None:
    draft = svc.create_request(session, make(employee, project, BIG, submit=False))
    svc.delete_request(session, draft.id)

    submitted = svc.create_request(session, make(employee, project, BIG))
    with pytest.raises(ConflictError):
        svc.delete_request(session, submitted.id)


def test_numbers_are_sequential_and_unique(session, employee, project) -> None:
    first = svc.create_request(session, make(employee, project, BIG))
    second = svc.create_request(session, make(employee, project, BIG))
    assert first.number == "РЗ-0001"
    assert second.number == "РЗ-0002"


def test_deleted_draft_does_not_free_its_number(session, employee, project) -> None:
    first = svc.create_request(session, make(employee, project, BIG, submit=False))
    svc.delete_request(session, first.id)
    session.flush()
    second = svc.create_request(session, make(employee, project, BIG))
    assert second.number == "РЗ-0002"


def test_limit_counts_only_priced_requests(session, employee, project, advance) -> None:
    """Пока закуп не назвал цену, тратить нечего — лимит не расходуется."""
    from app.services.reports import current_period

    year, month = current_period()
    waiting = svc.create_request(session, make(employee, project, BIG))
    session.flush()
    assert svc.spent_by_employee(session, employee.id, year=year, month=month) == Decimal(
        "0.00"
    )

    advance(waiting, to="priced", prices=PRICES)
    session.flush()
    assert svc.spent_by_employee(session, employee.id, year=year, month=month) == Decimal(
        "580.00"
    )


def test_rejected_and_stock_do_not_consume_limit(
    session, employee, project, advance
) -> None:
    from app.services.reports import current_period

    year, month = current_period()
    approved = svc.create_request(session, make(employee, project, BIG))
    advance(approved, to="approved", prices=PRICES)

    rejected = svc.create_request(session, make(employee, project, BIG))
    advance(rejected, to="priced", prices=PRICES)
    svc.decide_request(
        session, rejected.id, DecisionIn(approve=False, comment="Не по проекту")
    )

    from_stock = svc.create_request(session, make(employee, project, BIG))
    advance(from_stock, to="fulfilled", prices={})
    session.flush()

    spent = svc.spent_by_employee(session, employee.id, year=year, month=month)
    assert spent == Decimal("580.00")


def test_inactive_employee_cannot_submit(session, employee, project) -> None:
    employee.active = False
    session.flush()
    with pytest.raises(ValidationError):
        svc.create_request(session, make(employee, project, BIG))
