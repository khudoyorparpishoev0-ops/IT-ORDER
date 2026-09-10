"""Сколько ORDER AI стоит и приносит ли пользу.

Раздел «Расход AI» отвечает на один вопрос: продолжать за это платить
или нет. Поэтому здесь не «сколько запросов», а сколько денег, сколько
ответов приняли, сколько отказались и сколько обращений ORDER закрыл сам,
не потратив ничего.

## Откуда берутся числа

Из `ai_interactions` и `ai_feedback` — второго журнала не заводим. Ни
одной новой записи ради метрик здесь не появляется: считаем то, что и так
пишется на каждом обращении.

## Что считается стоимостью

Снимок `cost_usd`, записанный в момент обращения. Записи старше миграции
`0018` снимка не имеют — для них цена считается по нынешней таблице и
помечается как оценка (`estimated`). Смешивать снимок с сегодняшней ценой
молча нельзя: по этим цифрам сверяются со счётом Anthropic, и «почему у
вас на три доллара меньше» должно иметь ответ.

## Чего здесь нет

Подсказок из памяти заявок, шаблонов и проверки повторов. Это обычные
запросы к базе, они никогда не были обращениями к модели, и события их
нигде не записаны. Считать их «обработанными без модели» значило бы
завести второй журнал — а его заводить незачем. «Без модели» здесь
означает ровно одно: обращение к помощнику было, и ORDER ответил на него
сам — принятым алиасом или из кэша.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.time import month_bounds, to_local, utcnow
from app.db.models import AiFeedback, AiInteraction, AiResolvedBy
from app.services import ai_pricing
from app.services.ai_feedback import REASONS

#: Сколько людей показываем в разрезе по сотрудникам. Это техническая
#: метрика использования, а не рейтинг: длинный список превращает её в
#: доску позора, чего заказчик не просил и что данные не подтверждают.
EMPLOYEE_LIMIT = 10

#: Сколько причин отказа показываем.
REASON_LIMIT = 5

#: Подписи типов использования. Тип — это «какой помощник» плюс «откуда»:
#: одна и та же аналитика из панели и из ночной рассылки тратит деньги
#: по-разному, и складывать их в одну строку — значит не увидеть, за что
#: платим.
USAGE_LABEL: dict[tuple[str, str], str] = {
    ("MATERIAL", "WEB"): "Проверка написания материала",
    ("MATERIAL", "TELEGRAM"): "Проверка написания материала (бот)",
    ("REQUEST", "WEB"): "Разбор заявки в панели",
    ("REQUEST", "TELEGRAM"): "Заявка через бота",
    ("ANALYTICS", "WEB"): "Аналитика руководителя",
    ("ANALYTICS", "TELEGRAM"): "Аналитика в боте",
    ("ANALYTICS", "SCHEDULER"): "Автоматические сводки",
}


@dataclass(frozen=True)
class Period:
    """Показатели за отрезок времени."""

    label: str
    days: int
    requests: int
    cost_usd: Decimal
    #: Стоимость посчитана не по снимку, а по нынешней цене — записи до
    #: миграции 0018. Пусто — все суммы из снимков.
    estimated: bool
    input_tokens: int
    output_tokens: int
    avg_seconds: float | None
    error_pct: int | None
    #: Обращений, на которые ответили без модели.
    avoided: int
    avoided_pct: int | None


@dataclass(frozen=True)
class ModelRow:
    model: str | None
    requests: int
    cost_usd: Decimal
    avg_seconds: float | None
    #: Цена этой модели известна. False — сумма занижена, и это видно.
    price_known: bool


@dataclass(frozen=True)
class UsageRow:
    key: str
    label: str
    requests: int
    cost_usd: Decimal
    avg_tokens: int | None
    #: Доля применённых среди тех ответов, где кнопка «Применить» была.
    apply_rate_pct: int | None
    offered: int


@dataclass(frozen=True)
class EmployeeRow:
    employee: str
    requests: int
    tokens: int
    cost_usd: Decimal


@dataclass(frozen=True)
class Budget:
    """Бюджет месяца. Помощник по нему НЕ выключается."""

    limit_usd: Decimal | None
    spent_usd: Decimal
    used_pct: int | None
    warning_percent: int
    #: Порог пройден — администратору пора решать.
    warning: bool


@dataclass
class Usage:
    """Раздел «Расход AI» целиком."""

    periods: list[Period] = field(default_factory=list)
    models: list[ModelRow] = field(default_factory=list)
    usage_types: list[UsageRow] = field(default_factory=list)
    employees: list[EmployeeRow] = field(default_factory=list)
    feedback: dict = field(default_factory=dict)
    budget: Budget | None = None
    apply_rate_pct: int | None = None
    applied: int = 0
    offered: int = 0
    prices_checked: str = ai_pricing.PRICES_CHECKED


# --- Стоимость ------------------------------------------------------------------


def _cost_of(row: AiInteraction) -> tuple[Decimal, bool]:
    """Стоимость записи и признак «это оценка, а не снимок».

    Снимок главнее: цена, по которой платили, зафиксирована в момент
    обращения. Нынешняя таблица подставляется только там, где снимка нет
    вовсе — у записей старше миграции 0018.
    """
    if row.cost_usd is not None:
        return Decimal(row.cost_usd), False
    guess = ai_pricing.cost(row.model, row.input_tokens, row.output_tokens)
    if guess is None:
        return Decimal("0"), False
    return guess, True


def _rows(session: Session, since: datetime) -> list[AiInteraction]:
    return list(
        session.scalars(
            select(AiInteraction).where(AiInteraction.created_at >= since)
        )
    )


def _period(label: str, days: int, rows: list[AiInteraction]) -> Period:
    total = len(rows)
    failed = sum(1 for r in rows if not r.ok)

    cost = Decimal("0")
    estimated = False
    for row in rows:
        value, guessed = _cost_of(row)
        cost += value
        estimated = estimated or guessed

    waited = [r.duration_ms for r in rows if r.ok and r.duration_ms is not None]
    avoided = sum(
        1
        for r in rows
        if r.resolved_by in (AiResolvedBy.ALIAS, AiResolvedBy.CACHE)
    )

    return Period(
        label=label,
        days=days,
        requests=total,
        cost_usd=cost.quantize(Decimal("0.000001")),
        estimated=estimated,
        input_tokens=sum(r.input_tokens or 0 for r in rows),
        output_tokens=sum(r.output_tokens or 0 for r in rows),
        avg_seconds=round(sum(waited) / len(waited) / 1000, 1) if waited else None,
        error_pct=round(failed * 100 / total) if total else None,
        avoided=avoided,
        avoided_pct=round(avoided * 100 / total) if total else None,
    )


def _pct(part: int, whole: int) -> int | None:
    return round(part * 100 / whole) if whole else None


# --- Разрезы -----------------------------------------------------------------------


def _models(rows: list[AiInteraction]) -> list[ModelRow]:
    """Сколько стоит каждая модель. Сегодня их обычно одна.

    Модель в ORDER одна на всех помощников (`ASSISTANT_MODEL`), и вторая
    строка появится только после её смены. Разбивка всё равно нужна: по
    ней видно, что произошло со стоимостью после замены.
    """
    buckets: dict[str | None, list[AiInteraction]] = {}
    for row in rows:
        if row.resolved_by is not None and row.resolved_by is not AiResolvedBy.MODEL:
            # Алиас и кэш модели не касались — их место в «без модели»,
            # а не в разбивке по моделям.
            continue
        if not row.ok:
            # Отказ моделью не был: ответа не получили, платить не за
            # что. Отказы считаются отдельно долей ошибок — в разбивке
            # «сколько стоит каждая модель» они выглядели бы как
            # безымянная модель с неизвестной ценой, то есть враньём.
            continue
        buckets.setdefault(row.model, []).append(row)

    result: list[ModelRow] = []
    for model, items in buckets.items():
        cost = sum((_cost_of(r)[0] for r in items), Decimal("0"))
        waited = [r.duration_ms for r in items if r.duration_ms is not None]
        result.append(
            ModelRow(
                model=model,
                requests=len(items),
                cost_usd=cost.quantize(Decimal("0.000001")),
                avg_seconds=round(sum(waited) / len(waited) / 1000, 1) if waited else None,
                price_known=ai_pricing.price_of(model) is not None,
            )
        )
    result.sort(key=lambda m: (-m.requests, m.model or ""))
    return result


def _usage_types(rows: list[AiInteraction]) -> list[UsageRow]:
    """Разрез «за что платим»: какой помощник и откуда его звали."""
    buckets: dict[tuple[str, str], list[AiInteraction]] = {}
    for row in rows:
        buckets.setdefault((row.kind.value, row.source.value), []).append(row)

    result: list[UsageRow] = []
    for key, items in buckets.items():
        cost = sum((_cost_of(r)[0] for r in items), Decimal("0"))
        tokens = [
            (r.input_tokens or 0) + (r.output_tokens or 0)
            for r in items
            if r.input_tokens is not None or r.output_tokens is not None
        ]
        # Знаменатель — только те ответы, где кнопка «Применить» была.
        # У вопроса аналитику её нет, и включать его сюда значило бы
        # занижать долю у всех остальных.
        offered = [r for r in items if r.applied is not None]
        applied = [r for r in offered if r.applied]
        result.append(
            UsageRow(
                key=f"{key[0]}:{key[1]}",
                label=USAGE_LABEL.get(key, f"{key[0]} · {key[1]}"),
                requests=len(items),
                cost_usd=cost.quantize(Decimal("0.000001")),
                avg_tokens=round(sum(tokens) / len(tokens)) if tokens else None,
                apply_rate_pct=_pct(len(applied), len(offered)),
                offered=len(offered),
            )
        )
    result.sort(key=lambda u: (-u.cost_usd, -u.requests))
    return result


def _employees(rows: list[AiInteraction]) -> list[EmployeeRow]:
    """Кто сколько потратил. Это метрика использования, не оценка людей.

    Имя берётся из записи (`username`): сотрудника могли удалить, а
    расход остаётся — как и в журнале действий.
    """
    buckets: dict[str, list[AiInteraction]] = {}
    for row in rows:
        buckets.setdefault(row.username or "—", []).append(row)

    result = [
        EmployeeRow(
            employee=name,
            requests=len(items),
            tokens=sum((r.input_tokens or 0) + (r.output_tokens or 0) for r in items),
            cost_usd=sum((_cost_of(r)[0] for r in items), Decimal("0")).quantize(
                Decimal("0.000001")
            ),
        )
        for name, items in buckets.items()
    ]
    result.sort(key=lambda e: (-e.cost_usd, -e.requests))
    return result[:EMPLOYEE_LIMIT]


def _feedback(session: Session, since: datetime) -> dict:
    """Оценки людей за период."""
    useful, useless = session.execute(
        select(
            func.count().filter(AiFeedback.useful.is_(True)),
            func.count().filter(AiFeedback.useful.is_(False)),
        ).where(AiFeedback.created_at >= since)
    ).one()
    useful, useless = int(useful or 0), int(useless or 0)
    rated = useful + useless

    reasons = session.execute(
        select(AiFeedback.reason, func.count())
        .where(
            AiFeedback.created_at >= since,
            AiFeedback.useful.is_(False),
            AiFeedback.reason.is_not(None),
        )
        .group_by(AiFeedback.reason)
        .order_by(func.count().desc())
        .limit(REASON_LIMIT)
    ).all()

    answered = (
        session.scalar(
            select(func.count())
            .select_from(AiInteraction)
            .where(AiInteraction.created_at >= since, AiInteraction.ok.is_(True))
        )
        or 0
    )

    return {
        "useful": useful,
        "useless": useless,
        # Доля оценённых ответов: без неё «двенадцать против» невозможно
        # прочитать — двенадцать из пятнадцати и двенадцать из тысячи
        # означают разное.
        "feedback_rate_pct": _pct(rated, int(answered)),
        "useless_pct": _pct(useless, rated),
        "top_reasons": [
            {"reason": r, "label": REASONS.get(r, r), "count": int(c)}
            for r, c in reasons
        ],
    }


def _budget(session: Session, now: datetime) -> Budget:
    """Расход за календарный месяц против ожидаемого.

    Месяц считается по местному календарю (Душанбе), а не «последние 30
    дней»: счёт Anthropic приходит за календарный месяц, и сравнивать
    надо с ним.
    """
    settings = get_settings()
    start, end = month_bounds(to_local(now).year, to_local(now).month)
    rows = list(
        session.scalars(
            select(AiInteraction).where(
                AiInteraction.created_at >= start, AiInteraction.created_at < end
            )
        )
    )
    spent = sum((_cost_of(r)[0] for r in rows), Decimal("0"))
    limit = settings.ai_monthly_budget_usd
    limit = Decimal(limit) if limit and Decimal(limit) > 0 else None

    used_pct = None
    if limit is not None:
        used_pct = int((spent / limit * 100).to_integral_value(rounding="ROUND_HALF_UP"))

    return Budget(
        limit_usd=limit,
        spent_usd=spent.quantize(Decimal("0.000001")),
        used_pct=used_pct,
        warning_percent=settings.ai_budget_warning_percent,
        # Предупреждение и только: помощник продолжает работать. Порог —
        # повод человеку решить, а не системе отключить то, чем люди
        # пользуются посреди рабочего дня.
        warning=used_pct is not None and used_pct >= settings.ai_budget_warning_percent,
    )


# --- Сборка ----------------------------------------------------------------------------


def collect(session: Session, *, now: datetime | None = None) -> Usage:
    """Всё, что нужно разделу, одним проходом."""
    moment = now or utcnow()
    month_rows = _rows(session, moment - timedelta(days=30))
    week_rows = [r for r in month_rows if r.created_at >= moment - timedelta(days=7)]
    day_rows = [r for r in month_rows if r.created_at >= moment - timedelta(days=1)]

    offered = [r for r in month_rows if r.applied is not None]
    applied = [r for r in offered if r.applied]

    return Usage(
        periods=[
            _period("Сегодня", 1, day_rows),
            _period("7 дней", 7, week_rows),
            _period("30 дней", 30, month_rows),
        ],
        models=_models(month_rows),
        usage_types=_usage_types(month_rows),
        employees=_employees(month_rows),
        feedback=_feedback(session, moment - timedelta(days=30)),
        budget=_budget(session, moment),
        apply_rate_pct=_pct(len(applied), len(offered)),
        applied=len(applied),
        offered=len(offered),
    )
