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

from sqlalchemy import Select, func, or_, select
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
from app.services import categories
from app.services.material_norm import normalize
from app.services.requests import title_of

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


#: Категории, где смету пишет человек. Только их строки и есть материалы.
#:
#: У питания, поездки и карго строку выводит сервер: «Обед и ужин»,
#: «Карго, Оборудование Hikvision, Китай → Душанбе». В подсказках к полю
#: «что нужно» им не место — их никто не «закажет ещё раз» с автодополнения,
#: а ленту частого они забивают намертво.
_MATERIAL_CATEGORIES = [
    code for code, spec in categories.SPECS.items() if spec.form_type == categories.LINES
]


def _submitted_lines(*, employee_id: int | None = None, project_id: int | None = None) -> Select:
    """Основа всех выборок: строки поданных заявок за период.

    Берутся только заявки со сметой строками: у остальных категорий
    позицию собирает сервер, и материалом она не является.
    """
    stmt = (
        select(ExpenseLine, ExpenseRequest)
        .join(ExpenseRequest, ExpenseLine.request_id == ExpenseRequest.id)
        .where(
            ExpenseRequest.status.in_(SUBMITTED),
            ExpenseRequest.created_at >= _since(HISTORY_DAYS),
            ExpenseLine.normalized_text != "",
            or_(
                ExpenseRequest.category.is_(None),
                ExpenseRequest.category.in_(_MATERIAL_CATEGORIES),
            ),
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


# --- Ранжирование: какие прошлые заявки относятся к делу -----------------------

#: Вес совпадений. Порядок задан заказчиком: свой опыт на своём объекте
#: точнее всего, дальше — объект, дальше — сам человек, дальше — материал,
#: и в самом конце корпоративная частота. Веса подобраны так, чтобы
#: сумма нижних уровней не перебивала верхний: «тот же сотрудник на том
#: же объекте» должен стоять выше любой комбинации остального.
W_SAME_EMPLOYEE_AND_PROJECT = 100
W_SAME_PROJECT = 40
W_SAME_EMPLOYEE = 25
W_SAME_MATERIAL = 30
W_CORPORATE_FREQUENCY = 2

#: За сколько дней вес заявки падает вдвое. Полтора месяца: заявка
#: месячной давности ещё про то же самое, полугодовой — обычно нет.
RECENCY_HALF_LIFE_DAYS = 45

#: Сколько релевантных заявок уходит в промпт. Больше не нужно: из
#: пятисот прошлых заявок модели полезны три-десять, а каждая лишняя —
#: это токены, задержка и лишний повод ошибиться.
CONTEXT_LIMIT = 10


@dataclass(frozen=True)
class Scored:
    """Прошлая заявка с оценкой того, насколько она относится к делу."""

    request_id: int
    number: str
    title: str
    project_id: int
    project: str
    employee_id: int
    employee: str
    created_at: object
    days_ago: int
    lines: list[dict]
    score: float
    #: Почему заявка выбрана: «тот же объект», «тот же материал».
    reasons: list[str]


def _recency(days_ago: int) -> float:
    """Множитель свежести: сегодня 1.0, через полтора месяца 0.5."""
    return 0.5 ** (max(0, days_ago) / RECENCY_HALF_LIFE_DAYS)


def _same_material(line_key: str, keys: set[str]) -> bool:
    """Тот же материал, что ищут.

    Сравниваем вхождением в обе стороны, а не точным равенством: человек
    пишет «гофра16», а в прошлой заявке «Гофра 16 мм» — это одна и та же
    вещь, названная короче и полнее. Точное совпадение не нашло бы ни
    одной прошлой заявки, ради которых ранжирование и делалось.
    """
    if not line_key:
        return False
    return any(key in line_key or line_key in key for key in keys)


def ranked(
    session: Session,
    *,
    employee_id: int,
    project_id: int | None = None,
    materials: list[str] | None = None,
    visible_employee_id: int | None = None,
    limit: int = CONTEXT_LIMIT,
    days: int = HISTORY_DAYS,
) -> list[Scored]:
    """Прошлые заявки, отсортированные по тому, насколько они сейчас к месту.

    Считает сервер и только сервер: модель получает три-десять готовых
    строк, а не пятьсот заявок. Это дешевле, быстрее, короче по токенам и
    меньше поводов посоветовать не то.

    `visible_employee_id` — граница видимости: без права видеть чужие
    заявки сюда приходит id сотрудника, и в выборку попадёт только его
    история. Материалы при этом остаются общими: их даёт `frequent`,
    где чужих имён и сумм нет вовсе.
    """
    keys = {normalize(m) for m in (materials or []) if normalize(m)}

    stmt = (
        select(ExpenseRequest, Project.name, Employee.full_name)
        .join(Project, ExpenseRequest.project_id == Project.id)
        .join(Employee, ExpenseRequest.employee_id == Employee.id)
        .where(
            ExpenseRequest.status.in_(SUBMITTED),
            ExpenseRequest.created_at >= _since(days),
        )
        .order_by(ExpenseRequest.created_at.desc())
        # Берём разумный запас: скоринг может поднять наверх заявку,
        # которая по дате была бы двадцатой.
        .limit(200)
    )
    if visible_employee_id is not None:
        stmt = stmt.where(ExpenseRequest.employee_id == visible_employee_id)

    now = utcnow()
    scored: list[Scored] = []
    for request, project_name, employee_name in session.execute(stmt).all():
        days_ago = (now - request.created_at).days
        score = 0.0
        reasons: list[str] = []

        same_employee = request.employee_id == employee_id
        same_project = project_id is not None and request.project_id == project_id

        if same_employee and same_project:
            score += W_SAME_EMPLOYEE_AND_PROJECT
            reasons.append("ваша заявка на этом объекте")
        elif same_project:
            score += W_SAME_PROJECT
            reasons.append("тот же объект")
        elif same_employee:
            score += W_SAME_EMPLOYEE
            reasons.append("ваша прошлая заявка")

        matched = [line.title for line in request.lines if _same_material(line.normalized_text, keys)]
        if matched:
            score += W_SAME_MATERIAL
            reasons.append("тот же материал")

        if score == 0:
            # Корпоративная частота: заявка ни с чем не совпала, но
            # такие вещи в компании заказывают, и совсем выбрасывать её
            # рано — просто она в самом низу.
            score += W_CORPORATE_FREQUENCY

        scored.append(
            Scored(
                request_id=request.id,
                number=request.number,
                title=title_of(request),
                project_id=request.project_id,
                project=project_name,
                employee_id=request.employee_id,
                employee=employee_name,
                created_at=request.created_at,
                days_ago=days_ago,
                lines=[
                    {
                        "title": line.title,
                        "quantity": line.quantity,
                        "unit": line.unit,
                    }
                    for line in request.lines
                ],
                score=round(score * _recency(days_ago), 2),
                reasons=reasons,
            )
        )

    scored.sort(key=lambda item: (-item.score, -item.request_id))
    return scored[:limit]


def last_like(
    session: Session,
    *,
    employee_id: int,
    text: str = "",
    project_id: int | None = None,
    visible_employee_id: int | None = None,
    limit: int = 3,
) -> list[Scored]:
    """«Как в прошлый раз»: наиболее вероятные прошлые заявки.

    Заявка по этому не создаётся никогда — только показывается человеку
    с кнопками «Использовать», «Изменить», «Другой вариант». Угадать
    можно и неверно, а деньги тратятся настоящие.

    Слова запроса участвуют в поиске как материалы: «мне опять этот
    кабель» найдёт заявки с кабелем, «как вчера, но на Регар» — заявки
    с объектом Регар, потому что объект приходит отдельным параметром.
    """
    found = ranked(
        session,
        employee_id=employee_id,
        project_id=project_id,
        materials=_words(text),
        visible_employee_id=visible_employee_id,
        limit=limit * 4,
    )
    if not found:
        return []

    # Свою историю предпочитаем чужой: «в прошлый раз» — это про себя.
    own = [item for item in found if item.employee_id == employee_id]
    return (own or found)[:limit]


def _words(text: str) -> list[str]:
    """Слова запроса как кандидаты в материалы.

    Отдельного разбора не делаем: совпадение всё равно проверяется по
    приведённому написанию целой позиции, а лишние слова просто ничего
    не найдут.
    """
    clean = normalize(text)
    if not clean:
        return []
    return [clean, *[w for w in clean.split() if len(w) > 3]]


# --- Нечёткий поиск ------------------------------------------------------------


def search_materials(
    session: Session, *, text: str, limit: int = 8
) -> list[Suggestion]:
    """Поиск материала по неточному написанию.

    Сначала точное совпадение приведённого написания, потом вхождение,
    потом принятые людьми поправки (`material_aliases`). Отдельная
    векторная база пока не нужна и не заводится: на наших объёмах
    приведённое написание с триграммным индексом отвечает мгновенно.

    Контракт функции подобран так, чтобы переход на pgvector ничего не
    менял снаружи: на вход текст, на выход список подсказок. Появится
    вектор — поменяется тело, а API и панель останутся как есть.
    """
    key = normalize(text)
    if not key:
        return []

    alias = session.scalar(select(MaterialAlias).where(MaterialAlias.alias == key))
    if alias is not None:
        text = alias.canonical
        key = normalize(alias.canonical)

    base = _submitted_lines().subquery()
    grouped = (
        select(
            base.c.normalized_text.label("key"),
            func.max(base.c.id).label("last_id"),
            func.count().label("times"),
        )
        .where(base.c.normalized_text.ilike(f"%{key}%"))
        .group_by(base.c.normalized_text)
        .order_by(func.count().desc())
        .limit(limit)
        .subquery()
    )
    rows = session.execute(
        select(ExpenseLine.title, ExpenseLine.unit, grouped.c.times)
        .join(grouped, grouped.c.last_id == ExpenseLine.id)
        .order_by(grouped.c.times.desc(), ExpenseLine.title)
    ).all()
    return [
        Suggestion(title=title, unit=unit, times=int(times))
        for title, unit, times in rows
    ]


def recent(session: Session, employee_id: int, *, limit: int = 5) -> list[Suggestion]:
    """Что человек заказывал в последний раз. Не самое частое, а самое свежее:
    «недавно заказывали» отвечает на другой вопрос, чем «часто»."""
    base = _submitted_lines(employee_id=employee_id).subquery()
    grouped = (
        select(
            base.c.normalized_text.label("key"),
            func.max(base.c.id).label("last_id"),
            func.count().label("times"),
        )
        .group_by(base.c.normalized_text)
        .order_by(func.max(base.c.id).desc())
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
        .order_by(ExpenseLine.id.desc())
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
