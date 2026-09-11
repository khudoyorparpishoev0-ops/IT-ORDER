"""Склад: остаток считается из движений и меньше нуля не бывает.

Главное, что здесь проверяется, — не «работают ли кнопки», а два
свойства, ради которых модуль и написан:

* остаток нельзя задать, его можно только подвинуть документом;
* при одновременной выдаче последнего мешка выигрывает один, а не оба.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.errors import ConflictError, ValidationError
from app.db.models import (
    AuditLog,
    StockDocKind,
    StockDocStatus,
    StockDocument,
    StockItem,
    StockMove,
    StockMoveKind,
    Warehouse,
)
from app.schemas.stock import (
    DocumentLineIn,
    IssueIn,
    ReceiptIn,
    ReturnIn,
    StockItemIn,
    StockItemUpdate,
    WarehouseUpdate,
)
from app.services import stock as svc


def line(title: str, quantity: str, price: str | None = None, **kw) -> DocumentLineIn:
    return DocumentLineIn(
        title=title, quantity=Decimal(quantity), price=Decimal(price) if price else None, **kw
    )


def receipt(session, warehouse, *lines) -> StockDocument:
    return svc.create_receipt(
        session, ReceiptIn(warehouse_id=warehouse.id, lines=list(lines))
    )


def left(session, warehouse, name: str) -> Decimal:
    item = svc.find_item(session, name)
    assert item is not None, f"позиция «{name}» не заведена"
    return svc.available(session, warehouse_id=warehouse.id, item_id=item.id)


# --------------------------------------------------------------------------
# Остаток появляется из движений
# --------------------------------------------------------------------------
def test_receipt_raises_balance(session, warehouse) -> None:
    receipt(session, warehouse, line("Цемент М500", "40", "85.00"))
    assert left(session, warehouse, "Цемент М500") == Decimal("40.000")


def test_issue_lowers_balance(session, warehouse, employee, project) -> None:
    receipt(session, warehouse, line("Цемент М500", "40", "85.00"))
    svc.create_issue(
        session,
        IssueIn(
            warehouse_id=warehouse.id,
            recipient_id=employee.id,
            project_id=project.id,
            lines=[line("Цемент М500", "12")],
        ),
    )
    assert left(session, warehouse, "Цемент М500") == Decimal("28.000")


def test_return_raises_balance_back(session, warehouse, employee) -> None:
    receipt(session, warehouse, line("Гофра 16 мм", "100", "3.50"))
    svc.create_issue(
        session,
        IssueIn(
            warehouse_id=warehouse.id,
            recipient_id=employee.id,
            lines=[line("Гофра 16 мм", "40")],
        ),
    )
    svc.create_return(
        session,
        ReturnIn(
            warehouse_id=warehouse.id,
            recipient_id=employee.id,
            lines=[line("Гофра 16 мм", "15")],
        ),
    )
    assert left(session, warehouse, "Гофра 16 мм") == Decimal("75.000")


def test_balance_equals_sum_of_moves(session, warehouse, employee) -> None:
    """Остаток — свёртка ленты, а не отдельная правда. Разойдись они —
    верить нельзя ни той, ни другой."""
    receipt(session, warehouse, line("Кабель UTP Cat6", "500", "4.20"))
    svc.create_issue(
        session,
        IssueIn(
            warehouse_id=warehouse.id,
            recipient_id=employee.id,
            lines=[line("Кабель UTP Cat6", "120.5")],
        ),
    )
    item = svc.find_item(session, "Кабель UTP Cat6")
    moved = session.scalar(
        select(text("sum(quantity)")).select_from(StockMove).where(
            StockMove.item_id == item.id
        )
    )
    assert Decimal(moved) == svc.available(
        session, warehouse_id=warehouse.id, item_id=item.id
    )


def test_fractional_quantity_survives(session, warehouse) -> None:
    """Кабель метрами: 12,5 — не 12 и не 13."""
    receipt(session, warehouse, line("Кабель ВВГ 3х2.5", "12.5", "18.00"))
    assert left(session, warehouse, "Кабель ВВГ 3х2.5") == Decimal("12.500")


# --------------------------------------------------------------------------
# Меньше нуля не бывает
# --------------------------------------------------------------------------
def test_issue_more_than_available_refused(session, warehouse, employee) -> None:
    receipt(session, warehouse, line("Цемент М500", "10", "85.00"))
    with pytest.raises(ConflictError) as exc:
        svc.create_issue(
            session,
            IssueIn(
                warehouse_id=warehouse.id,
                recipient_id=employee.id,
                lines=[line("Цемент М500", "11")],
            ),
        )
    assert "не хватает" in str(exc.value)


def test_refused_issue_leaves_nothing_behind(session, warehouse, employee) -> None:
    """Отказ должен быть полным: ни остатка, ни номера, ни документа."""
    receipt(session, warehouse, line("Цемент М500", "10", "85.00"))
    # Приход фиксируем: откатывается неудавшаяся выдача, а не всё подряд —
    # именно так это выглядит в запросе, где откат делает слой API.
    session.commit()
    with pytest.raises(ConflictError):
        svc.create_issue(
            session,
            IssueIn(
                warehouse_id=warehouse.id,
                recipient_id=employee.id,
                lines=[line("Цемент М500", "11")],
            ),
        )
    session.rollback()
    assert left(session, warehouse, "Цемент М500") == Decimal("10.000")
    issued = session.scalars(
        select(StockDocument).where(StockDocument.kind == StockDocKind.ISSUE)
    ).all()
    assert issued == []


def test_database_itself_refuses_negative_balance(session, warehouse) -> None:
    """Последняя линия обороны: минус не запишется и прямым SQL."""
    receipt(session, warehouse, line("Цемент М500", "5", "85.00"))
    item = svc.find_item(session, "Цемент М500")
    session.flush()
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "UPDATE stock_balances SET quantity = -1 "
                "WHERE warehouse_id = :w AND item_id = :i"
            ),
            {"w": warehouse.id, "i": item.id},
        )
        session.flush()
    session.rollback()


def test_partial_document_does_not_apply(session, warehouse, employee) -> None:
    """Одна строка из трёх не проходит — не проходит весь документ."""
    receipt(
        session,
        warehouse,
        line("Цемент М500", "10", "85.00"),
        line("Гофра 16 мм", "100", "3.50"),
    )
    session.commit()
    with pytest.raises(ConflictError):
        svc.create_issue(
            session,
            IssueIn(
                warehouse_id=warehouse.id,
                recipient_id=employee.id,
                lines=[line("Гофра 16 мм", "10"), line("Цемент М500", "999")],
            ),
        )
    session.rollback()
    assert left(session, warehouse, "Гофра 16 мм") == Decimal("100.000")


# --------------------------------------------------------------------------
# Одновременная выдача
# --------------------------------------------------------------------------
def test_two_keepers_cannot_issue_the_same_last_bag(
    session, engine, warehouse, employee
) -> None:
    """Два кладовщика выдают последние 10 мешков одновременно.

    Ровно один должен получить отказ. Проверяем настоящими параллельными
    транзакциями через тот же сервис, которым пользуется панель: в одной
    сессии этот случай не воспроизводится вовсе, а именно он и ломает
    склад в жизни.
    """
    receipt(session, warehouse, line("Цемент М500", "10", "85.00"))
    item = svc.find_item(session, "Цемент М500")
    session.commit()

    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    barrier = threading.Barrier(2)
    outcome: list[str] = []
    lock = threading.Lock()

    def issue() -> None:
        db = factory()
        try:
            barrier.wait(timeout=10)
            svc.create_issue(
                db,
                IssueIn(
                    warehouse_id=warehouse.id,
                    recipient_id=employee.id,
                    lines=[line("Цемент М500", "6")],
                ),
            )
            db.commit()
            with lock:
                outcome.append("ok")
        except ConflictError:
            db.rollback()
            with lock:
                outcome.append("refused")
        finally:
            db.close()

    threads = [threading.Thread(target=issue) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(outcome) == ["ok", "refused"], outcome
    session.expire_all()
    assert svc.available(session, warehouse_id=warehouse.id, item_id=item.id) == Decimal(
        "4.000"
    )


# --------------------------------------------------------------------------
# Документы неизменяемы
# --------------------------------------------------------------------------
def test_cancel_reverses_but_keeps_moves(session, warehouse) -> None:
    document = receipt(session, warehouse, line("Цемент М500", "40", "85.00"))
    svc.cancel_document(session, document.id, reason="Привезли не то")

    assert left(session, warehouse, "Цемент М500") == Decimal("0.000")
    document = svc.get_document(session, document.id)
    assert document.status is StockDocStatus.CANCELLED
    assert document.cancel_reason == "Привезли не то"

    kinds = [
        move.kind
        for move in session.scalars(
            select(StockMove).order_by(StockMove.id).where(
                StockMove.document_id == document.id
            )
        )
    ]
    # Ошибка и исправление обе остались в ленте: по складу должно быть
    # видно не только «сколько есть», но и что здесь произошло.
    assert kinds == [StockMoveKind.RECEIPT, StockMoveKind.REVERSAL]


def test_cancel_twice_refused(session, warehouse) -> None:
    document = receipt(session, warehouse, line("Цемент М500", "5", "85.00"))
    svc.cancel_document(session, document.id, reason="Ошибка приёмки")
    with pytest.raises(ConflictError):
        svc.cancel_document(session, document.id, reason="Ещё раз")


def test_cancel_needs_reason(session, warehouse) -> None:
    document = receipt(session, warehouse, line("Цемент М500", "5", "85.00"))
    with pytest.raises(ValidationError):
        svc.cancel_document(session, document.id, reason="  ")


def test_cancel_refused_when_goods_already_issued(
    session, warehouse, employee
) -> None:
    """Приход отменить нельзя, если товар уже выдали: остаток ушёл бы в минус,
    а минус на складе — это не число, это потерянный учёт."""
    document = receipt(session, warehouse, line("Цемент М500", "10", "85.00"))
    svc.create_issue(
        session,
        IssueIn(
            warehouse_id=warehouse.id,
            recipient_id=employee.id,
            lines=[line("Цемент М500", "8")],
        ),
    )
    with pytest.raises(ConflictError):
        svc.cancel_document(session, document.id, reason="Вернули поставщику")


def test_numbers_say_what_the_document_is(session, warehouse, employee) -> None:
    first = receipt(session, warehouse, line("Цемент М500", "10", "85.00"))
    issue = svc.create_issue(
        session,
        IssueIn(
            warehouse_id=warehouse.id,
            recipient_id=employee.id,
            lines=[line("Цемент М500", "1")],
        ),
    )
    assert first.number.startswith("ПР-")
    assert issue.number.startswith("ВД-")
    assert first.number != issue.number


# --------------------------------------------------------------------------
# Номенклатура
# --------------------------------------------------------------------------
def test_same_material_written_differently_is_one_pile(session, warehouse) -> None:
    """«Цемент М500» и «цемент м-500» — одна куча, а не два остатка."""
    receipt(session, warehouse, line("Цемент М500", "40", "85.00"))
    receipt(session, warehouse, line("цемент м-500", "10", "86.00"))
    items = session.scalars(select(StockItem)).all()
    assert len(items) == 1
    assert left(session, warehouse, "Цемент М500") == Decimal("50.000")


def test_duplicate_line_merges(session, warehouse) -> None:
    document = receipt(
        session,
        warehouse,
        line("Цемент М500", "10", "85.00"),
        line("Цемент М500", "5", "85.00"),
    )
    assert len(document.lines) == 1
    assert document.lines[0].quantity == Decimal("15.000")
    assert left(session, warehouse, "Цемент М500") == Decimal("15.000")


def test_item_cannot_be_disabled_while_on_shelf(session, warehouse) -> None:
    receipt(session, warehouse, line("Цемент М500", "40", "85.00"))
    item = svc.find_item(session, "Цемент М500")
    with pytest.raises(ConflictError):
        svc.update_item(session, item.id, StockItemUpdate(active=False))


def test_warehouse_cannot_be_disabled_while_stocked(session, warehouse) -> None:
    receipt(session, warehouse, line("Цемент М500", "40", "85.00"))
    with pytest.raises(ConflictError):
        svc.update_warehouse(session, warehouse.id, WarehouseUpdate(active=False))


def test_second_item_with_same_name_refused(session) -> None:
    svc.create_item(session, StockItemIn(name="Цемент М500", unit="меш."))
    with pytest.raises(ConflictError):
        svc.create_item(session, StockItemIn(name="цемент  м500", unit="меш."))


def test_low_stock_is_seen(session, warehouse) -> None:
    item = svc.create_item(
        session, StockItemIn(name="Перчатки", unit="пар", min_quantity=Decimal("50"))
    )
    receipt(session, warehouse, DocumentLineIn(item_id=item.id, quantity=Decimal("20")))
    low = svc.list_items(session, low_only=True)
    assert [entry[0].name for entry in low] == ["Перчатки"]


# --------------------------------------------------------------------------
# Журнал
# --------------------------------------------------------------------------
def test_every_document_leaves_a_trace(session, warehouse) -> None:
    receipt(session, warehouse, line("Цемент М500", "40", "85.00"))
    actions = [
        row.action
        for row in session.scalars(
            select(AuditLog).where(AuditLog.entity == "stock_document")
        )
    ]
    assert actions == ["stock_receipt"]


def test_issue_price_is_not_invented(session, warehouse, employee) -> None:
    """Выдача со склада денег не стоит: заявка их уже посчитала."""
    receipt(session, warehouse, line("Цемент М500", "40", "85.00"))
    document = svc.create_issue(
        session,
        IssueIn(
            warehouse_id=warehouse.id,
            recipient_id=employee.id,
            lines=[line("Цемент М500", "5", "999.00")],
        ),
    )
    assert document.lines[0].price is None
    assert document.total is None


def test_warehouse_must_be_active(session, warehouse) -> None:
    warehouse.active = False
    session.flush()
    with pytest.raises(ValidationError):
        receipt(session, warehouse, line("Цемент М500", "1", "85.00"))


def test_unknown_warehouse_is_not_found(session) -> None:
    from app.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        svc.create_receipt(
            session, ReceiptIn(warehouse_id=9999, lines=[line("Цемент", "1")])
        )


def test_balances_hide_empty_by_default(session, warehouse) -> None:
    document = receipt(session, warehouse, line("Цемент М500", "5", "85.00"))
    svc.cancel_document(session, document.id, reason="Ошиблись складом")
    assert svc.balances(session, warehouse_id=warehouse.id) == []
    assert len(svc.balances(session, warehouse_id=warehouse.id, hide_empty=False)) == 1


def test_stock_value_uses_last_receipt_price(session, warehouse) -> None:
    receipt(session, warehouse, line("Цемент М500", "10", "80.00"))
    receipt(session, warehouse, line("Цемент М500", "10", "90.00"))
    assert svc.stock_value(session) == Decimal("1800.00")


def test_overview_counts_what_matters(session, warehouse) -> None:
    receipt(session, warehouse, line("Цемент М500", "10", "80.00"))
    data = svc.overview(session)
    assert data["warehouses"] == 1
    assert data["items"] == 1
    assert data["moves_today"] == 1


def test_warehouse_list_keeps_order(session, warehouse) -> None:
    session.add(Warehouse(name="Склад на Рекова"))
    session.flush()
    names = [w.name for w in svc.list_warehouses(session)]
    assert names == sorted(names)
