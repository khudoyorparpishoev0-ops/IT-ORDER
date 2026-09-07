"""Жизненный цикл заявки: переходы статусов, автоодобрение, суммы."""

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
)
from app.services import requests as svc


def make(employee, project, lines, submit=True) -> RequestCreate:
    return RequestCreate(
        employee_id=employee.id,
        project_id=project.id,
        lines=[ExpenseLineIn(**line) for line in lines],
        submit=submit,
    )


BIG = [
    {"title": "Проездной туда и обратно", "quantity": 1, "price": "150.00"},
    {"title": "Обед на одного", "quantity": 1, "price": "30.00"},
    {"title": "Материалы для работы", "quantity": 5, "price": "120.00"},
    {"title": "Такси до объекта", "quantity": 2, "price": "535.00"},
]
SMALL = [{"title": "Такси", "quantity": 1, "price": "300.00"}]


def test_amount_is_sum_of_lines(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    # 150 + 30 + 5*120 + 2*535 = 1850
    assert request.amount == Decimal("1850.00")
    assert [line.total for line in request.lines] == [
        Decimal("150.00"),
        Decimal("30.00"),
        Decimal("600.00"),
        Decimal("1070.00"),
    ]


def test_above_threshold_waits_for_decision(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    assert request.status is RequestStatus.PENDING
    assert request.submitted_at is not None
    assert request.decided_at is None


def test_at_or_below_threshold_auto_approved(session, employee, project) -> None:
    """Порог 500,00: заявка на 300 закрывается без руководителя."""
    request = svc.create_request(session, make(employee, project, SMALL))
    assert request.status is RequestStatus.APPROVED
    assert request.decided_by == svc.SYSTEM_ACTOR
    kinds = [e.kind for e in request.events]
    assert EventKind.AUTO_APPROVED in kinds


def test_threshold_boundary_is_inclusive(session, employee, project) -> None:
    exact = [{"title": "Ровно порог", "quantity": 1, "price": "500.00"}]
    request = svc.create_request(session, make(employee, project, exact))
    assert request.status is RequestStatus.APPROVED

    over = [{"title": "На копейку выше", "quantity": 1, "price": "500.01"}]
    request2 = svc.create_request(session, make(employee, project, over))
    assert request2.status is RequestStatus.PENDING


def test_draft_is_not_submitted(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG, submit=False))
    assert request.status is RequestStatus.DRAFT
    assert request.submitted_at is None


def test_approve_moves_to_approved(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    svc.decide_request(
        session, request.id, DecisionIn(approve=True, actor="Артём Ковалёв")
    )
    session.refresh(request)
    assert request.status is RequestStatus.APPROVED
    assert request.decided_by == "Артём Ковалёв"


def test_reject_requires_comment(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    # Схема ловит пустой комментарий ещё до сервиса
    with pytest.raises(ValueError):
        DecisionIn(approve=False, comment="   ")
    # Сервис проверяет то же самое, если его вызвали в обход схемы
    with pytest.raises(ValidationError):
        svc.decide_request(
            session, request.id, DecisionIn.model_construct(approve=False, comment=None)
        )


def test_reject_stores_comment(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    svc.decide_request(
        session,
        request.id,
        DecisionIn(approve=False, comment="Нет чеков, приложите до 10.09", actor="Артём"),
    )
    session.refresh(request)
    assert request.status is RequestStatus.REJECTED
    assert "чеков" in (request.decision_comment or "")


def test_decision_only_once(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    svc.decide_request(session, request.id, DecisionIn(approve=True))
    with pytest.raises(ConflictError):
        svc.decide_request(session, request.id, DecisionIn(approve=True))


def test_payment_requires_approved(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    payment = PaymentIn(method=PaymentMethod.CARD, document="ПП-0412")
    with pytest.raises(ConflictError):
        svc.pay_request(session, request.id, payment)

    svc.decide_request(session, request.id, DecisionIn(approve=True))
    svc.pay_request(session, request.id, payment)
    session.refresh(request)
    assert request.status is RequestStatus.PAID
    assert request.payment is not None
    assert request.payment.amount == request.amount


def test_payment_only_once(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    svc.decide_request(session, request.id, DecisionIn(approve=True))
    payment = PaymentIn(method=PaymentMethod.CASH, document="РКО-118")
    svc.pay_request(session, request.id, payment)
    with pytest.raises(ConflictError):
        svc.pay_request(session, request.id, payment)


def test_submitted_request_cannot_be_edited(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG))
    with pytest.raises(ConflictError):
        svc.update_request(
            session,
            request.id,
            RequestUpdate(lines=[ExpenseLineIn(title="Другое", quantity=1, price="10.00")]),
        )


def test_draft_can_be_edited_and_recalculated(session, employee, project) -> None:
    request = svc.create_request(session, make(employee, project, BIG, submit=False))
    svc.update_request(
        session,
        request.id,
        RequestUpdate(lines=[ExpenseLineIn(title="Только такси", quantity=3, price="100.00")]),
    )
    assert request.amount == Decimal("300.00")
    assert len(request.lines) == 1


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
    """Номер удалённого черновика не должен достаться другой заявке:
    черновик мог быть распечатан или отправлен до удаления."""
    first = svc.create_request(session, make(employee, project, BIG, submit=False))
    svc.delete_request(session, first.id)
    session.flush()
    second = svc.create_request(session, make(employee, project, BIG))
    assert second.number == "РЗ-0002"


def test_rejected_does_not_consume_limit(session, employee, project) -> None:
    from app.services.reports import current_period

    year, month = current_period()
    approved = svc.create_request(session, make(employee, project, BIG))
    svc.decide_request(session, approved.id, DecisionIn(approve=True))

    rejected = svc.create_request(session, make(employee, project, BIG))
    svc.decide_request(
        session, rejected.id, DecisionIn(approve=False, comment="Не по проекту")
    )
    session.flush()

    spent = svc.spent_by_employee(session, employee.id, year=year, month=month)
    assert spent == Decimal("1850.00")


def test_draft_does_not_consume_limit(session, employee, project) -> None:
    from app.services.reports import current_period

    year, month = current_period()
    svc.create_request(session, make(employee, project, BIG, submit=False))
    session.flush()
    assert svc.spent_by_employee(session, employee.id, year=year, month=month) == Decimal("0.00")


def test_inactive_employee_cannot_submit(session, employee, project) -> None:
    employee.active = False
    session.flush()
    with pytest.raises(ValidationError):
        svc.create_request(session, make(employee, project, BIG))
