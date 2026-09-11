"""Склад: номенклатура, остатки, приход, выдача, возврат.

Остаток здесь только читается. Эндпоинта, который принимал бы новое
значение остатка, нет вовсе — его меняют документы, и это не вопрос
права доступа, а вопрос того, что такое остаток.

Закупочная стоимость закрыта отдельным правом: остаток «цемент,
40 мешков» нужен многим, «запас на 32 000 сомони» — не всем из них.
Прячет её сервер, а не панель: спрятанное на клиенте видно в ответе.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, RequirePermission, bind_audit_actor
from app.core.permissions import Permission, has_permission
from app.db.models import (
    Employee,
    StockDocKind,
    StockDocument,
    StockItem,
    Warehouse,
)
from app.schemas.stock import (
    BalanceOut,
    CancelIn,
    DocumentDetailOut,
    DocumentLineOut,
    DocumentOut,
    IssueIn,
    ItemCardOut,
    MoveOut,
    ReceiptIn,
    ReturnIn,
    StockItemIn,
    StockItemOut,
    StockItemUpdate,
    StockOverviewOut,
    WarehouseIn,
    WarehouseOut,
    WarehouseUpdate,
)
from app.services import stock as svc

router = APIRouter(
    prefix="/api/stock", tags=["stock"], dependencies=[Depends(bind_audit_actor)]
)

view = Depends(RequirePermission(Permission.VIEW_STOCK))
manage = Depends(RequirePermission(Permission.MANAGE_STOCK))
manage_reference = Depends(RequirePermission(Permission.MANAGE_REFERENCE))


def _sees_cost(user: Employee) -> bool:
    return has_permission(user.role, Permission.VIEW_STOCK_COST)


def _warehouse_out(
    warehouse: Warehouse, *, items_count: int = 0, value=None
) -> WarehouseOut:
    return WarehouseOut(
        id=warehouse.id,
        name=warehouse.name,
        project_id=warehouse.project_id,
        project_name=warehouse.project.name if warehouse.project else None,
        address=warehouse.address,
        keeper_id=warehouse.keeper_id,
        keeper_name=warehouse.keeper.full_name if warehouse.keeper else None,
        active=warehouse.active,
        items_count=items_count,
        value=value,
    )


def _item_out(item: StockItem, quantity) -> StockItemOut:
    return StockItemOut(
        id=item.id,
        name=item.name,
        unit=item.unit,
        article=item.article,
        min_quantity=item.min_quantity,
        track_serial=item.track_serial,
        active=item.active,
        note=item.note,
        quantity=quantity,
        low=bool(item.min_quantity > 0 and quantity < item.min_quantity),
    )


def _document_out(document: StockDocument, *, cost: bool) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        number=document.number,
        kind=document.kind,
        status=document.status,
        warehouse_id=document.warehouse_id,
        warehouse_name=document.warehouse.name if document.warehouse else "",
        created_by=document.created_by,
        recipient_name=document.recipient.full_name if document.recipient else None,
        project_name=document.project.name if document.project else None,
        supplier=document.supplier,
        comment=document.comment,
        total=document.total if cost else None,
        lines_count=len(document.lines),
        created_at=document.created_at,
        cancelled_at=document.cancelled_at,
        cancelled_by=document.cancelled_by,
        cancel_reason=document.cancel_reason,
    )


def _detail_out(document: StockDocument, *, cost: bool) -> DocumentDetailOut:
    base = _document_out(document, cost=cost)
    return DocumentDetailOut(
        **base.model_dump(),
        lines=[
            DocumentLineOut(
                id=line.id,
                item_id=line.item_id,
                item_name=line.item.name if line.item else "",
                unit=line.item.unit if line.item else "",
                quantity=line.quantity,
                price=line.price if cost else None,
                total=line.total if cost else None,
                comment=line.comment,
            )
            for line in document.lines
        ],
    )


def _move_out(move, document, item, warehouse, *, cost: bool) -> MoveOut:
    return MoveOut(
        id=move.id,
        document_id=document.id,
        document_number=document.number,
        kind=move.kind,
        warehouse_id=warehouse.id,
        warehouse_name=warehouse.name,
        item_id=item.id,
        item_name=item.name,
        unit=item.unit,
        quantity=move.quantity,
        price=move.price if cost else None,
        actor=move.actor,
        created_at=move.created_at,
    )


# --------------------------------------------------------------------------
# Обзор
# --------------------------------------------------------------------------
@router.get("/overview", response_model=StockOverviewOut, dependencies=[view])
def overview(session: DbSession, user: CurrentUser):
    data = svc.overview(session)
    return StockOverviewOut(
        **data, value=svc.stock_value(session) if _sees_cost(user) else None
    )


# --------------------------------------------------------------------------
# Места хранения
# --------------------------------------------------------------------------
@router.get("/warehouses", response_model=list[WarehouseOut], dependencies=[view])
def list_warehouses(
    session: DbSession, user: CurrentUser, only_active: bool = Query(default=False)
):
    counts = svc.warehouse_item_counts(session)
    return [
        _warehouse_out(warehouse, items_count=counts.get(warehouse.id, 0))
        for warehouse in svc.list_warehouses(session, only_active=only_active)
    ]


@router.post(
    "/warehouses",
    response_model=WarehouseOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[manage_reference],
)
def create_warehouse(session: DbSession, _: CurrentUser, data: WarehouseIn):
    """Склады заводит администратор: это структура компании, как объекты."""
    warehouse = svc.create_warehouse(session, data)
    session.commit()
    session.refresh(warehouse)
    return _warehouse_out(warehouse)


@router.patch(
    "/warehouses/{warehouse_id}",
    response_model=WarehouseOut,
    dependencies=[manage_reference],
)
def update_warehouse(
    session: DbSession, _: CurrentUser, warehouse_id: int, data: WarehouseUpdate
):
    warehouse = svc.update_warehouse(session, warehouse_id, data)
    session.commit()
    session.refresh(warehouse)
    return _warehouse_out(warehouse)


# --------------------------------------------------------------------------
# Номенклатура и остатки
# --------------------------------------------------------------------------
@router.get("/items", response_model=list[StockItemOut], dependencies=[view])
def list_items(
    session: DbSession,
    _: CurrentUser,
    search: str | None = Query(default=None, max_length=100),
    only_active: bool = Query(default=False),
    low_only: bool = Query(default=False),
):
    rows = svc.list_items(
        session, search=search, only_active=only_active, low_only=low_only
    )
    return [_item_out(item, quantity) for item, quantity in rows]


@router.post(
    "/items",
    response_model=StockItemOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[manage],
)
def create_item(session: DbSession, _: CurrentUser, data: StockItemIn):
    """Позицию заводит кладовщик: она появляется в момент приёмки, и ждать
    администратора на каждой новой марке кабеля нельзя."""
    item = svc.create_item(session, data)
    session.commit()
    session.refresh(item)
    return _item_out(item, 0)


@router.patch("/items/{item_id}", response_model=StockItemOut, dependencies=[manage])
def update_item(session: DbSession, _: CurrentUser, item_id: int, data: StockItemUpdate):
    item = svc.update_item(session, item_id, data)
    session.commit()
    session.refresh(item)
    quantity = sum(
        (qty for _w, _i, qty in svc.balances(session, item_id=item.id, hide_empty=False)),
        start=0,
    )
    return _item_out(item, quantity)


@router.get("/items/{item_id}", response_model=ItemCardOut, dependencies=[view])
def item_card(session: DbSession, user: CurrentUser, item_id: int):
    """Карточка позиции: где лежит и что с ней происходило."""
    item = svc.get_item(session, item_id)
    rows = svc.balances(session, item_id=item.id, hide_empty=False)
    total = sum((quantity for _w, _i, quantity in rows), start=0)
    cost = _sees_cost(user)
    return ItemCardOut(
        item=_item_out(item, total),
        balances=[
            BalanceOut(
                warehouse_id=warehouse.id,
                warehouse_name=warehouse.name,
                item_id=item.id,
                item_name=item.name,
                unit=item.unit,
                quantity=quantity,
                low=bool(item.min_quantity > 0 and total < item.min_quantity),
            )
            for warehouse, _item, quantity in rows
        ],
        moves=[
            _move_out(move, document, moved_item, warehouse, cost=cost)
            for move, document, moved_item, warehouse in svc.list_moves(
                session, item_id=item.id, limit=50
            )
        ],
    )


@router.get("/balances", response_model=list[BalanceOut], dependencies=[view])
def list_balances(
    session: DbSession,
    _: CurrentUser,
    warehouse_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    hide_empty: bool = Query(default=True),
):
    return [
        BalanceOut(
            warehouse_id=warehouse.id,
            warehouse_name=warehouse.name,
            item_id=item.id,
            item_name=item.name,
            unit=item.unit,
            quantity=quantity,
            low=bool(item.min_quantity > 0 and quantity < item.min_quantity),
        )
        for warehouse, item, quantity in svc.balances(
            session, warehouse_id=warehouse_id, search=search, hide_empty=hide_empty
        )
    ]


# --------------------------------------------------------------------------
# Движения
# --------------------------------------------------------------------------
@router.get("/moves", response_model=list[MoveOut], dependencies=[view])
def list_moves(
    session: DbSession,
    user: CurrentUser,
    item_id: int | None = Query(default=None),
    warehouse_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    cost = _sees_cost(user)
    return [
        _move_out(move, document, item, warehouse, cost=cost)
        for move, document, item, warehouse in svc.list_moves(
            session, item_id=item_id, warehouse_id=warehouse_id, limit=limit
        )
    ]


# --------------------------------------------------------------------------
# Документы
# --------------------------------------------------------------------------
@router.get("/documents", response_model=list[DocumentOut], dependencies=[view])
def list_documents(
    session: DbSession,
    user: CurrentUser,
    kind: StockDocKind | None = Query(default=None),
    warehouse_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, _total = svc.list_documents(
        session,
        kind=kind,
        warehouse_id=warehouse_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    cost = _sees_cost(user)
    return [_document_out(document, cost=cost) for document in rows]


@router.post(
    "/receipts",
    response_model=DocumentDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[manage],
)
def create_receipt(session: DbSession, user: CurrentUser, data: ReceiptIn):
    """Приход: привезли на склад."""
    document = svc.create_receipt(session, data)
    session.commit()
    return _detail_out(svc.get_document(session, document.id), cost=_sees_cost(user))


@router.post(
    "/issues",
    response_model=DocumentDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[manage],
)
def create_issue(session: DbSession, user: CurrentUser, data: IssueIn):
    """Выдача: со склада человеку на объект."""
    document = svc.create_issue(session, data)
    session.commit()
    return _detail_out(svc.get_document(session, document.id), cost=_sees_cost(user))


@router.post(
    "/returns",
    response_model=DocumentDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[manage],
)
def create_return(session: DbSession, user: CurrentUser, data: ReturnIn):
    """Возврат: не пригодилось, вернули на склад."""
    document = svc.create_return(session, data)
    session.commit()
    return _detail_out(svc.get_document(session, document.id), cost=_sees_cost(user))


@router.post(
    "/documents/{document_id}/cancel",
    response_model=DocumentDetailOut,
    dependencies=[manage],
)
def cancel_document(
    session: DbSession, user: CurrentUser, document_id: int, data: CancelIn
):
    """Отмена обратными движениями. Документ не удаляется: проведённое
    движение остаётся в ленте, иначе по складу нельзя доказать ничего."""
    document = svc.cancel_document(session, document_id, reason=data.reason)
    session.commit()
    return _detail_out(svc.get_document(session, document.id), cost=_sees_cost(user))


@router.get(
    "/documents/{document_id}", response_model=DocumentDetailOut, dependencies=[view]
)
def get_document(session: DbSession, user: CurrentUser, document_id: int):
    return _detail_out(svc.get_document(session, document_id), cost=_sees_cost(user))
