"""Склад: номенклатура, места хранения, движения и остатки.

Главное правило модуля: **остаток — это следствие движений, а не поле,
которое кто-то правит**. Функции, принимающей новое значение остатка,
здесь нет и не будет. Человек оформляет приход, выдачу или возврат —
остаток меняется сам, и по ленте всегда видно, откуда он такой взялся.

Отсюда же неизменяемость: проведённый документ не правится и не
удаляется. Ошибка исправляется отменой (сторно), которая добавляет
обратные движения, а прежние оставляет на месте. То же правило, что у
`audit_log` и `request_events`: запись, которую можно поправить задним
числом, ничего не доказывает.

Конкурентный остаток решается тремя слоями, и нижний — база:

1. `SELECT … FOR UPDATE` по строке остатка: вторая выдача ждёт первую;
2. `INSERT … ON CONFLICT DO UPDATE` — гонку на создании строки остатка
   разрешает база, а не проверка «а есть ли такая строка»;
3. `CHECK (quantity >= 0)` на самой таблице — минус не запишется, даже
   если оба слоя выше обойдут.

Строки документа применяются в порядке номера позиции: две выдачи с
пересекающимся составом берут блокировки в одном и том же порядке и не
встают друг против друга.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.audit_context import current_actor
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.money import to_decimal
from app.core.quantity import quantity as quantity_text
from app.core.quantity import to_quantity
from app.core.time import local_date, local_day_bounds, utcnow
from app.db.models import (
    STOCK_DOCUMENT_NUMBER_SEQ,
    Employee,
    Project,
    StockBalance,
    StockDocKind,
    StockDocStatus,
    StockDocument,
    StockDocumentLine,
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
    WarehouseIn,
    WarehouseUpdate,
)
from app.services.audit import write_audit
from app.services.material_norm import normalize

ZERO = Decimal("0.000")

#: Приставка номера документа по виду. «ПР-0007» читается без словаря,
#: а по одному сквозному номеру нельзя понять, приход это или выдача.
NUMBER_PREFIX: dict[StockDocKind, str] = {
    StockDocKind.RECEIPT: "ПР",
    StockDocKind.ISSUE: "ВД",
    StockDocKind.RETURN: "ВЗ",
}

#: Вид движения по виду документа.
MOVE_KIND: dict[StockDocKind, StockMoveKind] = {
    StockDocKind.RECEIPT: StockMoveKind.RECEIPT,
    StockDocKind.ISSUE: StockMoveKind.ISSUE,
    StockDocKind.RETURN: StockMoveKind.RETURN,
}

#: Знак количества: приход и возврат прибавляют, выдача убавляет.
SIGN: dict[StockDocKind, int] = {
    StockDocKind.RECEIPT: 1,
    StockDocKind.ISSUE: -1,
    StockDocKind.RETURN: 1,
}

DOC_LABEL: dict[StockDocKind, str] = {
    StockDocKind.RECEIPT: "Приход",
    StockDocKind.ISSUE: "Выдача",
    StockDocKind.RETURN: "Возврат",
}


# --------------------------------------------------------------------------
# Места хранения
# --------------------------------------------------------------------------
def list_warehouses(session: Session, *, only_active: bool = False) -> list[Warehouse]:
    stmt = select(Warehouse).options(
        selectinload(Warehouse.project), selectinload(Warehouse.keeper)
    ).order_by(Warehouse.name)
    if only_active:
        stmt = stmt.where(Warehouse.active.is_(True))
    return list(session.scalars(stmt))


def warehouse_item_counts(session: Session) -> dict[int, int]:
    """Сколько позиций лежит на каждом складе. Одним запросом, а не
    выборкой всех остатков с подсчётом в Python: складов десяток, а
    строк остатка со временем тысячи."""
    rows = session.execute(
        select(StockBalance.warehouse_id, func.count())
        .where(StockBalance.quantity > 0)
        .group_by(StockBalance.warehouse_id)
    )
    return {warehouse_id: count for warehouse_id, count in rows}


def get_warehouse(session: Session, warehouse_id: int) -> Warehouse:
    warehouse = session.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise NotFoundError("Склад не найден")
    return warehouse


def _check_keeper(session: Session, keeper_id: int | None) -> Employee | None:
    if keeper_id is None:
        return None
    keeper = session.get(Employee, keeper_id)
    if keeper is None:
        raise NotFoundError("Сотрудник не найден")
    if not keeper.active:
        raise ValidationError("Уволенный сотрудник не может быть ответственным за склад")
    return keeper


def _check_project(session: Session, project_id: int | None) -> Project | None:
    if project_id is None:
        return None
    project = session.get(Project, project_id)
    if project is None:
        raise NotFoundError("Объект не найден")
    return project


def create_warehouse(session: Session, data: WarehouseIn) -> Warehouse:
    name = " ".join((data.name or "").split())
    if not name:
        raise ValidationError("Название склада не может быть пустым")
    if session.scalar(select(Warehouse).where(func.lower(Warehouse.name) == name.lower())):
        raise ConflictError(f"Склад «{name}» уже заведён")

    _check_project(session, data.project_id)
    _check_keeper(session, data.keeper_id)

    warehouse = Warehouse(
        name=name,
        project_id=data.project_id,
        address=(data.address or "").strip() or None,
        keeper_id=data.keeper_id,
        active=data.active,
    )
    session.add(warehouse)
    session.flush()
    write_audit(
        session, entity="warehouse", entity_id=warehouse.id, action="create", details=name
    )
    return warehouse


def update_warehouse(
    session: Session, warehouse_id: int, data: WarehouseUpdate
) -> Warehouse:
    warehouse = get_warehouse(session, warehouse_id)
    changes: list[str] = []

    if data.name is not None:
        name = " ".join(data.name.split())
        if not name:
            raise ValidationError("Название склада не может быть пустым")
        taken = session.scalar(
            select(Warehouse).where(
                func.lower(Warehouse.name) == name.lower(), Warehouse.id != warehouse.id
            )
        )
        if taken:
            raise ConflictError(f"Склад «{name}» уже заведён")
        if name != warehouse.name:
            changes.append(f"название: {warehouse.name} → {name}")
            warehouse.name = name

    if data.project_id is not None:
        _check_project(session, data.project_id)
        warehouse.project_id = data.project_id
        changes.append("объект изменён")

    if data.address is not None:
        warehouse.address = data.address.strip() or None

    if data.keeper_id is not None:
        keeper = _check_keeper(session, data.keeper_id)
        warehouse.keeper_id = data.keeper_id
        changes.append(f"ответственный: {keeper.full_name if keeper else '—'}")

    if data.active is not None and data.active != warehouse.active:
        # Отключаем, а не удаляем: склад живёт в документах, а они
        # неизменяемы. Остаток на отключённом складе никуда не девается —
        # его сначала перемещают или списывают.
        if not data.active and _stock_left(session, warehouse.id) > 0:
            raise ConflictError(
                "На складе есть остаток. Сначала выдайте или переместите его"
            )
        warehouse.active = data.active
        changes.append("работает" if data.active else "отключён")

    session.flush()
    write_audit(
        session,
        entity="warehouse",
        entity_id=warehouse.id,
        action="update",
        details=f"{warehouse.name}: {', '.join(changes)}" if changes else warehouse.name,
    )
    return warehouse


def _stock_left(session: Session, warehouse_id: int) -> Decimal:
    total = session.scalar(
        select(func.coalesce(func.sum(StockBalance.quantity), 0)).where(
            StockBalance.warehouse_id == warehouse_id
        )
    )
    return to_quantity(total or 0)


# --------------------------------------------------------------------------
# Номенклатура
# --------------------------------------------------------------------------
def list_items(
    session: Session,
    *,
    search: str | None = None,
    only_active: bool = False,
    low_only: bool = False,
    limit: int = 500,
) -> list[tuple[StockItem, Decimal]]:
    """Позиции с общим остатком по всем складам."""
    totals = (
        select(
            StockBalance.item_id.label("item_id"),
            func.sum(StockBalance.quantity).label("quantity"),
        )
        .group_by(StockBalance.item_id)
        .subquery()
    )
    stmt = (
        select(StockItem, func.coalesce(totals.c.quantity, 0))
        .outerjoin(totals, totals.c.item_id == StockItem.id)
        .order_by(StockItem.name)
        .limit(limit)
    )
    if only_active:
        stmt = stmt.where(StockItem.active.is_(True))
    if search:
        needle = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(StockItem.name).like(needle),
                StockItem.normalized_name.like(f"%{normalize(search)}%"),
                func.lower(func.coalesce(StockItem.article, "")).like(needle),
            )
        )
    if low_only:
        stmt = stmt.where(
            StockItem.min_quantity > 0,
            func.coalesce(totals.c.quantity, 0) < StockItem.min_quantity,
        )
    return [(item, to_quantity(qty or 0)) for item, qty in session.execute(stmt)]


def get_item(session: Session, item_id: int) -> StockItem:
    item = session.get(StockItem, item_id)
    if item is None:
        raise NotFoundError("Позиция не найдена")
    return item


def find_item(session: Session, title: str) -> StockItem | None:
    """Позиция по написанию — тем же приведением, что у строк заявки.

    «Цемент М500» и «цемент м-500» — одна куча на складе. Если бы ключом
    была строка как её набрали, куча немедленно расползлась бы на пять
    остатков, и каждый был бы неверен.
    """
    key = normalize(title)
    if not key:
        return None
    return session.scalar(select(StockItem).where(StockItem.normalized_name == key))


def create_item(session: Session, data: StockItemIn) -> StockItem:
    name = " ".join((data.name or "").split())
    if not name:
        raise ValidationError("Название позиции не может быть пустым")
    key = normalize(name)
    if not key:
        raise ValidationError("Название позиции состоит из одних знаков препинания")

    existing = session.scalar(select(StockItem).where(StockItem.normalized_name == key))
    if existing is not None:
        raise ConflictError(f"Такая позиция уже есть: «{existing.name}»")

    item = StockItem(
        name=name,
        normalized_name=key,
        unit=(data.unit or "шт.").strip() or "шт.",
        article=(data.article or "").strip() or None,
        min_quantity=to_quantity(data.min_quantity or 0),
        track_serial=data.track_serial,
        note=(data.note or "").strip() or None,
    )
    session.add(item)
    session.flush()
    write_audit(
        session, entity="stock_item", entity_id=item.id, action="create", details=name
    )
    return item


def update_item(session: Session, item_id: int, data: StockItemUpdate) -> StockItem:
    item = get_item(session, item_id)
    changes: list[str] = []

    if data.name is not None:
        name = " ".join(data.name.split())
        if not name:
            raise ValidationError("Название позиции не может быть пустым")
        key = normalize(name)
        taken = session.scalar(
            select(StockItem).where(
                StockItem.normalized_name == key, StockItem.id != item.id
            )
        )
        if taken is not None:
            raise ConflictError(f"Такая позиция уже есть: «{taken.name}»")
        if name != item.name:
            changes.append(f"название: {item.name} → {name}")
        item.name = name
        item.normalized_name = key

    if data.unit is not None:
        unit = data.unit.strip() or "шт."
        if unit != item.unit:
            changes.append(f"единица: {item.unit} → {unit}")
        item.unit = unit

    if data.article is not None:
        item.article = data.article.strip() or None
    if data.min_quantity is not None:
        item.min_quantity = to_quantity(data.min_quantity)
        changes.append(f"минимальный остаток: {quantity_text(item.min_quantity)}")
    if data.track_serial is not None:
        item.track_serial = data.track_serial
    if data.note is not None:
        item.note = data.note.strip() or None
    if data.active is not None and data.active != item.active:
        if not data.active and _item_left(session, item.id) > 0:
            raise ConflictError("Позиция ещё лежит на складе: остаток не нулевой")
        item.active = data.active
        changes.append("в работе" if data.active else "отключена")

    session.flush()
    write_audit(
        session,
        entity="stock_item",
        entity_id=item.id,
        action="update",
        details=f"{item.name}: {', '.join(changes)}" if changes else item.name,
    )
    return item


def _item_left(session: Session, item_id: int) -> Decimal:
    total = session.scalar(
        select(func.coalesce(func.sum(StockBalance.quantity), 0)).where(
            StockBalance.item_id == item_id
        )
    )
    return to_quantity(total or 0)


# --------------------------------------------------------------------------
# Остатки
# --------------------------------------------------------------------------
def balances(
    session: Session,
    *,
    warehouse_id: int | None = None,
    item_id: int | None = None,
    search: str | None = None,
    hide_empty: bool = True,
    limit: int = 500,
) -> list[tuple[Warehouse, StockItem, Decimal]]:
    stmt = (
        select(Warehouse, StockItem, StockBalance.quantity)
        .join(StockBalance, StockBalance.warehouse_id == Warehouse.id)
        .join(StockItem, StockItem.id == StockBalance.item_id)
        .order_by(StockItem.name, Warehouse.name)
        .limit(limit)
    )
    if warehouse_id is not None:
        stmt = stmt.where(StockBalance.warehouse_id == warehouse_id)
    if item_id is not None:
        stmt = stmt.where(StockBalance.item_id == item_id)
    if hide_empty:
        stmt = stmt.where(StockBalance.quantity > 0)
    if search:
        needle = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(StockItem.name).like(needle),
                StockItem.normalized_name.like(f"%{normalize(search)}%"),
            )
        )
    return [
        (warehouse, item, to_quantity(qty))
        for warehouse, item, qty in session.execute(stmt)
    ]


def available(session: Session, *, warehouse_id: int, item_id: int) -> Decimal:
    """Сколько лежит. Читается без блокировки: это справка, а не решение
    о выдаче — решение принимается внутри транзакции документа."""
    value = session.scalar(
        select(StockBalance.quantity).where(
            StockBalance.warehouse_id == warehouse_id,
            StockBalance.item_id == item_id,
        )
    )
    return to_quantity(value or 0)


def stock_value(session: Session) -> Decimal:
    """Оценка запаса по последней известной цене прихода.

    Не средневзвешенная себестоимость: партионного учёта в ORDER нет, и
    делать вид, что он есть, значило бы выдать догадку за факт. Цифра
    называется оценкой и показывается только по праву видеть стоимость.
    """
    last_price = (
        select(
            StockDocumentLine.item_id.label("item_id"),
            StockDocumentLine.price.label("price"),
            func.row_number()
            .over(
                partition_by=StockDocumentLine.item_id,
                order_by=StockDocumentLine.id.desc(),
            )
            .label("rn"),
        )
        .join(StockDocument, StockDocument.id == StockDocumentLine.document_id)
        .where(
            StockDocument.kind == StockDocKind.RECEIPT,
            StockDocument.status == StockDocStatus.POSTED,
            StockDocumentLine.price.is_not(None),
        )
        .subquery()
    )
    prices = select(last_price).where(last_price.c.rn == 1).subquery()
    total = session.scalar(
        select(
            func.coalesce(
                func.sum(StockBalance.quantity * func.coalesce(prices.c.price, 0)), 0
            )
        ).select_from(StockBalance).outerjoin(prices, prices.c.item_id == StockBalance.item_id)
    )
    return to_decimal(total or 0)


# --------------------------------------------------------------------------
# Документы
# --------------------------------------------------------------------------
def next_number(session: Session, kind: StockDocKind) -> str:
    """«ПР-0007». Номер из последовательности базы, а не из max(number):
    последовательность не откатывается, и отменённый документ не вернёт
    свой номер в оборот."""
    value = session.scalar(STOCK_DOCUMENT_NUMBER_SEQ.next_value())
    return f"{NUMBER_PREFIX[kind]}-{value:04d}"


def _resolve_item(session: Session, line: DocumentLineIn) -> StockItem:
    """Позиция строки: по ссылке или по названию, заводя на лету.

    Кладовщик принимает товар, а не ведёт справочник: если бы новую
    марку кабеля нельзя было принять без администратора, приёмка встала
    бы до понедельника.
    """
    if line.item_id is not None:
        item = session.get(StockItem, line.item_id)
        if item is None:
            raise NotFoundError("Позиция не найдена")
        if not item.active:
            raise ValidationError(f"Позиция «{item.name}» отключена")
        return item

    title = " ".join((line.title or "").split())
    if not title:
        raise ValidationError("У строки нет ни позиции, ни названия")
    found = find_item(session, title)
    if found is not None:
        if not found.active:
            raise ValidationError(f"Позиция «{found.name}» отключена")
        return found
    return create_item(
        session, StockItemIn(name=title, unit=(line.unit or "шт.").strip() or "шт.")
    )


def _apply_balance(
    session: Session, *, warehouse: Warehouse, item: StockItem, delta: Decimal, now: datetime
) -> Decimal:
    """Меняет остаток на `delta` и возвращает новый. Отрицательным не бывает."""
    locked = session.execute(
        select(StockBalance.quantity)
        .where(
            StockBalance.warehouse_id == warehouse.id,
            StockBalance.item_id == item.id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    current = to_quantity(locked) if locked is not None else ZERO

    if current + delta < 0:
        raise ConflictError(
            f"На складе «{warehouse.name}» не хватает: {item.name} — "
            f"есть {quantity_text(current)} {item.unit}, "
            f"нужно {quantity_text(-delta)} {item.unit}"
        )

    table = StockBalance.__table__
    try:
        if locked is None:
            # Строки остатка ещё нет. Вставляем — и гонку на её создании
            # разрешает база: соседняя транзакция успела первой, значит
            # наше количество прибавится к её, а не затрёт его.
            #
            # Здесь `delta` всегда положительна: отрицательная при нулевом
            # остатке отсеяна проверкой выше. Это важно не для красоты —
            # PostgreSQL проверяет CHECK у предлагаемой строки ДО того,
            # как разберётся с конфликтом, и вставка «−12» упала бы,
            # не дойдя до сложения.
            stmt = (
                pg_insert(table)
                .values(
                    warehouse_id=warehouse.id,
                    item_id=item.id,
                    quantity=delta,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    constraint="uq_stock_balance_pair",
                    set_={"quantity": table.c.quantity + delta, "updated_at": now},
                )
                .returning(table.c.quantity)
            )
        else:
            # Строка есть и заблокирована нами: прибавляем прямо в базе,
            # а не записываем вычисленное в Python. Считает всегда база —
            # так между чтением и записью не помещается чужая выдача.
            stmt = (
                table.update()
                .where(
                    table.c.warehouse_id == warehouse.id,
                    table.c.item_id == item.id,
                )
                .values(quantity=table.c.quantity + delta, updated_at=now)
                .returning(table.c.quantity)
            )
        result = session.execute(stmt).scalar_one()
    except IntegrityError as exc:
        # Сработало ограничение базы — последняя линия обороны. Сюда
        # попадаем, если проверка выше уже не могла помочь: остаток
        # изменила соседняя транзакция.
        raise ConflictError(
            f"На складе «{warehouse.name}» не хватает: {item.name}"
        ) from exc
    return to_quantity(result)


def _post(
    session: Session,
    *,
    kind: StockDocKind,
    warehouse_id: int,
    lines: list[DocumentLineIn],
    recipient_id: int | None = None,
    project_id: int | None = None,
    supplier: str | None = None,
    comment: str | None = None,
    request_id: int | None = None,
) -> StockDocument:
    """Создаёт проведённый документ и его движения.

    Черновика нет намеренно: склад с «почти оформленным приходом» — это
    остаток, которому нельзя верить. Кладовщик оформляет по факту, когда
    товар уже приехал, а ошибку исправляет отменой и новым документом.
    """
    warehouse = get_warehouse(session, warehouse_id)
    if not warehouse.active:
        raise ValidationError(f"Склад «{warehouse.name}» отключён")

    recipient: Employee | None = None
    if recipient_id is not None:
        recipient = session.get(Employee, recipient_id)
        if recipient is None:
            raise NotFoundError("Сотрудник не найден")
    _check_project(session, project_id)

    actor = current_actor()
    now = utcnow()

    document = StockDocument(
        number=next_number(session, kind),
        kind=kind,
        status=StockDocStatus.POSTED,
        warehouse_id=warehouse.id,
        employee_id=actor.id if actor else None,
        created_by=(actor.name if actor else None),
        recipient_id=recipient.id if recipient else None,
        project_id=project_id,
        request_id=request_id,
        supplier=(supplier or "").strip() or None,
        comment=(comment or "").strip() or None,
    )
    session.add(document)
    session.flush()

    sign = SIGN[kind]
    total = Decimal("0.00")
    has_price = False
    seen: dict[int, StockDocumentLine] = {}

    prepared: list[tuple[StockItem, DocumentLineIn]] = [
        (_resolve_item(session, line), line) for line in lines
    ]
    # По номеру позиции: две выдачи с пересекающимся составом берут
    # блокировки в одном порядке и не встают друг против друга.
    prepared.sort(key=lambda pair: pair[0].id)

    for item, line in prepared:
        qty = to_quantity(line.quantity)
        if qty <= 0:
            raise ValidationError(f"Количество в строке «{item.name}» должно быть больше нуля")

        if item.id in seen:
            # Одна позиция дважды в одном документе — почти всегда
            # опечатка, а не замысел. Складываем, а не заводим две строки:
            # иначе остаток верен, а документ читается как ошибка.
            merged = seen[item.id]
            merged.quantity = to_quantity(merged.quantity + qty)
            if merged.price is not None:
                merged.total = to_decimal(merged.price * merged.quantity)
        else:
            price = to_decimal(line.price) if line.price is not None else None
            if price is not None and kind is not StockDocKind.RECEIPT:
                # Цену знает приход. Выдача со склада денег не стоит:
                # заявка их уже посчитала, и второй раз расход не считаем.
                price = None
            row = StockDocumentLine(
                document_id=document.id,
                item_id=item.id,
                quantity=qty,
                price=price,
                total=to_decimal(price * qty) if price is not None else None,
                comment=(line.comment or "").strip() or None,
            )
            session.add(row)
            seen[item.id] = row

        _apply_balance(
            session, warehouse=warehouse, item=item, delta=qty * sign, now=now
        )
        session.add(
            StockMove(
                document_id=document.id,
                warehouse_id=warehouse.id,
                item_id=item.id,
                kind=MOVE_KIND[kind],
                quantity=to_quantity(qty * sign),
                price=seen[item.id].price,
                employee_id=actor.id if actor else None,
                actor=actor.name if actor else None,
            )
        )

    for row in seen.values():
        if row.total is not None:
            total += row.total
            has_price = True

    document.total = total if has_price else None
    session.flush()
    # Остатки менялись мимо ORM (INSERT … ON CONFLICT), и загруженные
    # ранее объекты об этом не знают. Сбрасываем, чтобы следующее чтение
    # в этой же сессии не показало прежнюю цифру.
    session.expire_all()

    write_audit(
        session,
        entity="stock_document",
        entity_id=document.number,
        action=f"stock_{kind.value.lower()}",
        details=(
            f"{DOC_LABEL[kind]} {document.number}, склад «{warehouse.name}», "
            f"{len(seen)} поз."
        ),
    )
    return document


def create_receipt(session: Session, data: ReceiptIn) -> StockDocument:
    return _post(
        session,
        kind=StockDocKind.RECEIPT,
        warehouse_id=data.warehouse_id,
        lines=data.lines,
        supplier=data.supplier,
        comment=data.comment,
    )


def create_issue(session: Session, data: IssueIn) -> StockDocument:
    return _post(
        session,
        kind=StockDocKind.ISSUE,
        warehouse_id=data.warehouse_id,
        lines=data.lines,
        recipient_id=data.recipient_id,
        project_id=data.project_id,
        comment=data.comment,
    )


def create_return(session: Session, data: ReturnIn) -> StockDocument:
    return _post(
        session,
        kind=StockDocKind.RETURN,
        warehouse_id=data.warehouse_id,
        lines=data.lines,
        recipient_id=data.recipient_id,
        project_id=data.project_id,
        comment=data.comment,
    )


def cancel_document(session: Session, document_id: int, *, reason: str) -> StockDocument:
    """Отмена документа обратными движениями.

    Не удаление: проведённое движение остаётся в ленте навсегда, иначе по
    складу нельзя доказать ничего. Отмена добавляет к нему зеркальное
    движение вида REVERSAL — по ленте видно и ошибку, и исправление.
    """
    document = get_document(session, document_id)
    if document.status is StockDocStatus.CANCELLED:
        raise ConflictError(f"Документ {document.number} уже отменён")

    text = " ".join((reason or "").split())
    if len(text) < 3:
        raise ValidationError("Укажите причину отмены")

    warehouse = get_warehouse(session, document.warehouse_id)
    actor = current_actor()
    now = utcnow()
    sign = -SIGN[document.kind]

    for row in sorted(document.lines, key=lambda line: line.item_id):
        item = get_item(session, row.item_id)
        _apply_balance(
            session,
            warehouse=warehouse,
            item=item,
            delta=to_quantity(row.quantity) * sign,
            now=now,
        )
        session.add(
            StockMove(
                document_id=document.id,
                warehouse_id=document.warehouse_id,
                item_id=row.item_id,
                kind=StockMoveKind.REVERSAL,
                quantity=to_quantity(row.quantity * sign),
                price=row.price,
                employee_id=actor.id if actor else None,
                actor=actor.name if actor else None,
            )
        )

    document.status = StockDocStatus.CANCELLED
    document.cancelled_at = now
    document.cancelled_by = actor.name if actor else None
    document.cancel_reason = text
    session.flush()
    session.expire_all()

    write_audit(
        session,
        entity="stock_document",
        entity_id=document.number,
        action="stock_cancel",
        details=f"{DOC_LABEL[document.kind]} {document.number} отменён: {text}",
    )
    return document


def get_document(session: Session, document_id: int) -> StockDocument:
    document = session.get(
        StockDocument,
        document_id,
        options=[
            selectinload(StockDocument.lines).selectinload(StockDocumentLine.item),
            selectinload(StockDocument.warehouse),
            selectinload(StockDocument.recipient),
            selectinload(StockDocument.project),
        ],
    )
    if document is None:
        raise NotFoundError("Документ не найден")
    return document


def _documents_query() -> Select[tuple[StockDocument]]:
    return select(StockDocument).options(
        selectinload(StockDocument.warehouse),
        selectinload(StockDocument.recipient),
        selectinload(StockDocument.project),
        selectinload(StockDocument.lines),
    )


def list_documents(
    session: Session,
    *,
    kind: StockDocKind | None = None,
    warehouse_id: int | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[StockDocument], int]:
    stmt = _documents_query()
    count_stmt = select(func.count()).select_from(StockDocument)

    if kind is not None:
        stmt = stmt.where(StockDocument.kind == kind)
        count_stmt = count_stmt.where(StockDocument.kind == kind)
    if warehouse_id is not None:
        stmt = stmt.where(StockDocument.warehouse_id == warehouse_id)
        count_stmt = count_stmt.where(StockDocument.warehouse_id == warehouse_id)
    if search:
        needle = f"%{search.strip().lower()}%"
        where = or_(
            func.lower(StockDocument.number).like(needle),
            func.lower(func.coalesce(StockDocument.supplier, "")).like(needle),
            func.lower(func.coalesce(StockDocument.created_by, "")).like(needle),
        )
        stmt = stmt.where(where)
        count_stmt = count_stmt.where(where)

    total = session.scalar(count_stmt) or 0
    stmt = stmt.order_by(StockDocument.created_at.desc(), StockDocument.id.desc())
    rows = list(session.scalars(stmt.limit(limit).offset(offset)))
    return rows, total


def list_moves(
    session: Session,
    *,
    item_id: int | None = None,
    warehouse_id: int | None = None,
    limit: int = 100,
) -> list[tuple[StockMove, StockDocument, StockItem, Warehouse]]:
    stmt = (
        select(StockMove, StockDocument, StockItem, Warehouse)
        .join(StockDocument, StockDocument.id == StockMove.document_id)
        .join(StockItem, StockItem.id == StockMove.item_id)
        .join(Warehouse, Warehouse.id == StockMove.warehouse_id)
        .order_by(StockMove.created_at.desc(), StockMove.id.desc())
        .limit(limit)
    )
    if item_id is not None:
        stmt = stmt.where(StockMove.item_id == item_id)
    if warehouse_id is not None:
        stmt = stmt.where(StockMove.warehouse_id == warehouse_id)
    return list(session.execute(stmt))


def overview(session: Session) -> dict:
    """Первый экран склада: сколько складов, позиций и что заканчивается."""
    warehouses = session.scalar(
        select(func.count()).select_from(Warehouse).where(Warehouse.active.is_(True))
    )
    items = session.scalar(
        select(func.count()).select_from(StockItem).where(StockItem.active.is_(True))
    )
    low = len(list_items(session, only_active=True, low_only=True))
    # «Сегодня» — местное, а не UTC: в Душанбе смена начинается на пять
    # часов раньше, и date_trunc по серверному времени показывал бы
    # кладовщику вчерашние движения как сегодняшние до пяти утра.
    day_start, day_end = local_day_bounds(local_date(utcnow()))
    today = session.scalar(
        select(func.count())
        .select_from(StockMove)
        .where(StockMove.created_at >= day_start, StockMove.created_at < day_end)
    )
    return {
        "warehouses": warehouses or 0,
        "items": items or 0,
        "low_items": low,
        "moves_today": today or 0,
    }
