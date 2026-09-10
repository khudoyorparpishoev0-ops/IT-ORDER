"""Разрешённый набор запросов аналитики.

Модель не пишет SQL и не выполняет его. Она называет намерение из этого
списка — «покажи просроченные», «что изменилось за неделю», — а сервер
сам решает, какую функцию позвать и с какими правами.

Почему так, а не «дать Claude доступ к базе». SQL от модели — это
произвольный запрос в боевую базу от имени приложения: ни прав, ни
предсказуемости, ни возможности объяснить, откуда взялась цифра.
Намерение из списка, наоборот, всегда исполняется одним и тем же кодом,
который уже проверен тестами и уже знает про права.

Добавить новую возможность — значит добавить сюда функцию, а не
расширить модели свободу.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.services.analytics import anomalies, attention, executive
from app.services.analytics import inconsistencies as inc
from app.services.analytics import stale
from app.services.analytics.facts import (
    find_duplicates,
    in_work_briefs,
    people_stats,
    project_stats,
    stage_stats,
    totals,
    trends,
)
from app.services.analytics.scope import Scope

#: Сколько строк отдаём модели по одному намерению. Больше не нужно: из
#: длинного списка она всё равно пересказывает первые несколько, а
#: платить приходится за все.
ROWS_LIMIT = 15


@dataclass(frozen=True)
class Intent:
    """Одна разрешённая возможность аналитики."""

    name: str
    #: Для чего она — этот текст видит модель, выбирая намерение.
    description: str
    run: Callable[[Session, Scope, datetime], Any]


def _overview(session: Session, scope: Scope, now: datetime) -> Any:
    return executive.overview(session, now=now, scope=scope)


def _overdue(session: Session, scope: Scope, now: datetime) -> Any:
    rows = stale.stuck_requests(session, now=now, scope=scope)
    return [s for s in rows if s.overdue][:ROWS_LIMIT]


def _stuck(session: Session, scope: Scope, now: datetime) -> Any:
    rows = stale.stuck_requests(session, now=now, scope=scope)
    return [s for s in rows if not s.overdue][:ROWS_LIMIT]


def _attention(session: Session, scope: Scope, now: datetime) -> Any:
    return attention.requires_attention(session, now=now, scope=scope)[:ROWS_LIMIT]


def _inconsistencies(session: Session, scope: Scope, now: datetime) -> Any:
    rows = stale.in_work(session, scope=scope)
    return inc.find_all(session, now=now, rows=rows)[:ROWS_LIMIT]


def _duplicates(session: Session, scope: Scope, now: datetime) -> Any:
    del scope
    return find_duplicates(session, now=now)[:ROWS_LIMIT]


def _projects(session: Session, scope: Scope, now: datetime) -> Any:
    del scope
    return project_stats(session, now=now)[:ROWS_LIMIT]


def _employees(session: Session, scope: Scope, now: datetime) -> Any:
    del scope
    return people_stats(session, now=now)[:ROWS_LIMIT]


def _expenses(session: Session, scope: Scope, now: datetime) -> Any:
    del scope
    return totals(session, now=now)


def _stages(session: Session, scope: Scope, now: datetime) -> Any:
    del scope
    return stage_stats(session, now=now)


def _compare(session: Session, scope: Scope, now: datetime) -> Any:
    del scope
    return {"trends": trends(session, now=now), "anomalies": anomalies.find(session, now=now)}


def _requests(session: Session, scope: Scope, now: datetime) -> Any:
    del scope
    return in_work_briefs(session, now=now)


REGISTRY: dict[str, Intent] = {
    intent.name: intent
    for intent in (
        Intent("overview", "Общее состояние: активные, созданные, закрытые, просроченные", _overview),
        Intent("overdue", "Заявки, вышедшие за норматив своего этапа", _overdue),
        Intent("stuck", "Заявки без движения, норматив ещё не нарушен", _stuck),
        Intent("attention", "Всё, что требует внимания, одной очередью", _attention),
        Intent("inconsistencies", "Нестыковки: чего в заявке не хватает или что не сходится", _inconsistencies),
        Intent("duplicates", "Возможные повторы заявок", _duplicates),
        Intent("project_summary", "Статистика по объектам: заявки, суммы, задержки", _projects),
        Intent("employee_summary", "Кто сколько держит заявок и сколько из них за нормативом", _employees),
        Intent("expense_summary", "Деньги: к оплате, оплачено за месяц, бюджет", _expenses),
        Intent("stage_summary", "Этапы пути заявки против нормативов", _stages),
        Intent("compare_periods", "Что изменилось к прошлой неделе и что отличается от обычного", _compare),
        Intent("requests", "Список заявок в работе", _requests),
    )
}

#: Намерение по умолчанию: если модель не назвала ничего внятного,
#: показываем общее состояние, а не отказ.
DEFAULT = "overview"


def names() -> list[str]:
    return list(REGISTRY)


def catalog() -> str:
    """Список намерений для промпта: имя и одна строка, что оно даёт."""
    return "\n".join(f"- {i.name}: {i.description}" for i in REGISTRY.values())


def run(session: Session, name: str, *, scope: Scope, now: datetime) -> Any:
    """Выполняет намерение. Неизвестное — не ошибка, а общее состояние.

    Модель может назвать несуществующее имя: она пишет текст, а не код.
    Падать из-за этого нечестно перед человеком, который просто задал
    вопрос, — показываем общую сводку.
    """
    intent = REGISTRY.get(name) or REGISTRY[DEFAULT]
    return intent.run(session, scope, now)
