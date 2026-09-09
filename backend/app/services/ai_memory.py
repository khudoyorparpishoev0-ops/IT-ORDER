"""Память ORDER: что уже заказывали, кто и на каком объекте.

Память помощника — это база ORDER, а не модель. Claude ничего не помнит
между запросами и к PostgreSQL не подключается: сервер собирает выжимку
по заявкам и отдаёт её текстом, как и в аналитике. Считает всегда сервер.

Главное следствие такого устройства: подсказки работают без модели
вообще. Кончился баланс, упал Anthropic, не задан ключ — «часто
заказываете», автодополнение и предупреждение о дубле продолжают
работать, потому что это обычные запросы к базе.

Права. Названия материалов общие: что в компании называют «Кабель UTP
Cat6», знать может каждый — иначе подсказки бессмысленны. А «кто, когда
и на сколько заказывал» — это чужая заявка, и она фильтруется тем же
правилом, что список заявок: без `view_all_requests` человек видит
только своё.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import (
    Employee,
    ExpenseLine,
    ExpenseRequest,
    MaterialAlias,
    Project,
    RequestStatus,
)
from app.services.material_norm import normalize

#: За какой срок собираем историю. Год назад заказывали другое и по
#: другим ценам, а подсказка из позапрошлого сезона только мешает.
HISTORY_DAYS = 180

#: Насколько недавняя заявка считается возможным дублем. Неделя: за это
#: время закуп ещё не успел закрыть первую, и вторая — почти наверняка
#: та же потребность, поданная дважды.
DUPLICATE_DAYS = 7

#: Черновик — ещё не потребность: его правят и удаляют. В памяти учитываем
#: только то, что человек действительно подал.
SUBMITTED = tuple(s for s in RequestStatus if s is not RequestStatus.DRAFT)


@dataclass(frozen=True)
class Suggestion:
    """Подсказка для поля «что нужно»."""

    title: str
    unit: str | None
    #: Сколько раз это заказывали за период.
    times: int
    #: Номер и дата последней заявки с этой позицией — чтобы человек
    #: понимал, откуда подсказка, и мог проверить.
    last_number: str | None = None
    last_date: str | None = None


@dataclass(frozen=True)
class SimilarRequest:
    """Недавняя заявка с теми же позициями. Решение — за человеком."""

    id: int
    number: str
    title: str
    project: str
    employee: str
    status: str
    days_ago: int
    #: Совпавшие позиции: по ним видно, о чём речь.
    materials: list[str]


def _since(days: int):
    return utcnow() - timedelta(days=days)


def _submitted_lines(*, employee_id: int | None = None, project_id: int | None = None) -> Select:
    """Основа всех выборок: строки поданных заявок за период."""
    stmt = (
        select(ExpenseLine, ExpenseRequest)
        .join(ExpenseRequest, ExpenseLine.request_id == ExpenseRequest.id)
        .where(
            ExpenseRequest.status.in_(SUBMITTED),
            ExpenseRequest.created_at >= _since(HISTORY_DAYS),
            ExpenseLine.normalized_text != "",
        )
    )
    if employee_id is not None:
        stmt = stmt.where(ExpenseRequest.employee_id == employee_id)
    if project_id is not None:
        stmt = stmt.where(ExpenseRequest.project_id == project_id)
    return stmt


def _grouped(
    session: Session,
    *,
    employee_id: int | None = None,
    project_id: int | None = None,
    limit: int = 12,
) -> list[Suggestion]:
    """Позиции, схлопнутые по приведённому написанию.

    Показываем написание из самой свежей заявки: иначе подсказка тянула
    бы за собой старую опечатку. Считаем по `normalized_text`, поэтому
    «гофра16» и «Гофра 16 мм» — одна подсказка, а не две.
    """
    base = _submitted_lines(employee_id=employee_id, project_id=project_id).subquery()
    grouped = (
        select(
            base.c.normalized_text.label("key"),
            func.max(base.c.id).label("last_id"),
            func.count().label("times"),
        )
        .group_by(base.c.normalized_text)
        .order_by(func.count().desc(), func.max(base.c.id).desc())
        .limit(limit)
        .subquery()
    )
    rows = session.execute(
        select(
            ExpenseLine.title,
            ExpenseLine.unit,
            grouped.c.times,
            ExpenseRequest.number,
            ExpenseRequest.created_at,
        )
        .join(grouped, grouped.c.last_id == ExpenseLine.id)
        .join(ExpenseRequest, ExpenseLine.request_id == ExpenseRequest.id)
        .order_by(grouped.c.times.desc(), ExpenseLine.title)
    ).all()
    return [
        Suggestion(
            title=title,
            unit=unit,
            times=int(times),
            last_number=number,
            last_date=created_at.date().isoformat(),
        )
        for title, unit, times, number, created_at in rows
    ]


def frequent(session: Session, *, project_id: int | None = None, limit: int = 8) -> list[Suggestion]:
    """Что просят чаще всего. Названия материалов не тайна — фильтра по
    автору здесь нет намеренно, иначе новый сотрудник не получил бы ни
    одной подсказки в свой первый день."""
    return _grouped(session, project_id=project_id, limit=limit)


def mine(session: Session, employee_id: int, *, limit: int = 8) -> list[Suggestion]:
    """Что заказывал сам сотрудник. Самая точная подсказка: люди повторяют
    свои же заявки чаще, чем чужие."""
    return _grouped(session, employee_id=employee_id, limit=limit)


def by_project(session: Session, project_id: int, *, limit: int = 8) -> list[Suggestion]:
    """Что заказывали на этом объекте. На стройке потребности объекта
    важнее личных привычек: соседняя бригада уже знает, что тут нужно."""
    return _grouped(session, project_id=project_id, limit=limit)


def similar_requests(
    session: Session,
    *,
    titles: list[str],
    project_id: int | None = None,
    employee_id: int | None = None,
    days: int = DUPLICATE_DAYS,
    limit: int = 3,
) -> list[SimilarRequest]:
    """Недавние заявки с теми же позициями.

    Отвечает на вопрос «это уже заказывали?» до подачи, а не после
    оплаты. Сравниваем по приведённому написанию: «гофра16» у одного и
    «Гофра 16 мм» у другого — одна и та же потребность.

    `employee_id` задаёт границу видимости: без права видеть чужие заявки
    сюда приходит id сотрудника, и он получает только свои.
    """
    keys = {normalize(t) for t in titles if normalize(t)}
    if not keys:
        return []

    stmt = (
        select(
            ExpenseRequest.id,
            ExpenseRequest.number,
            ExpenseRequest.status,
            ExpenseRequest.created_at,
            Project.name,
            Employee.full_name,
            func.array_agg(ExpenseLine.title.distinct()).label("materials"),
        )
        .join(ExpenseLine, ExpenseLine.request_id == ExpenseRequest.id)
        .join(Project, ExpenseRequest.project_id == Project.id)
        .join(Employee, ExpenseRequest.employee_id == Employee.id)
        .where(
            ExpenseRequest.status.in_(SUBMITTED),
            ExpenseRequest.created_at >= _since(days),
            ExpenseLine.normalized_text.in_(keys),
        )
        .group_by(
            ExpenseRequest.id,
            ExpenseRequest.number,
            ExpenseRequest.status,
            ExpenseRequest.created_at,
            Project.name,
            Employee.full_name,
        )
        .order_by(ExpenseRequest.created_at.desc())
        .limit(limit)
    )
    if project_id is not None:
        stmt = stmt.where(ExpenseRequest.project_id == project_id)
    if employee_id is not None:
        stmt = stmt.where(ExpenseRequest.employee_id == employee_id)

    now = utcnow()
    return [
        SimilarRequest(
            id=row.id,
            number=row.number,
            title=row.materials[0] if row.materials else "",
            project=row.name,
            employee=row.full_name,
            status=row.status.value,
            days_ago=(now - row.created_at).days,
            materials=sorted(row.materials or []),
        )
        for row in session.execute(stmt).all()
    ]


# --- Алиасы: поправки, которые люди приняли ----------------------------------


def alias_for(session: Session, title: str) -> MaterialAlias | None:
    """Как это называют в компании. None — такого написания ещё не правили."""
    key = normalize(title)
    if not key:
        return None
    return session.scalar(select(MaterialAlias).where(MaterialAlias.alias == key))


def remember_alias(session: Session, *, wrote: str, canonical: str, unit: str | None) -> None:
    """Запоминает принятую поправку.

    Зовётся, когда человек нажал «Применить» на совете помощника: значит,
    поправку признали верной именно люди. Руками эту таблицу никто не
    заполняет — справочник, который надо вести, устареет за месяц.
    """
    key = normalize(wrote)
    canonical = " ".join((canonical or "").split())
    if not key or not canonical or key == normalize(canonical):
        # Написание не изменилось — запоминать нечего.
        return

    existing = session.scalar(select(MaterialAlias).where(MaterialAlias.alias == key))
    if existing is None:
        session.add(
            MaterialAlias(
                alias=key[:200],
                canonical=canonical[:200],
                unit=(unit or "").strip() or None,
                uses=1,
            )
        )
        return
    existing.canonical = canonical[:200]
    existing.unit = (unit or "").strip() or existing.unit
    existing.uses += 1
    existing.updated_at = utcnow()
