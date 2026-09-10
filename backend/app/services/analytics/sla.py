"""Нормативы времени на этапах — одна точка на всё приложение.

Раньше нормативы читались из настроек в трёх местах, и «поменять SLA»
означало найти все три. Теперь их спрашивают здесь: и очередь внимания,
и заявки без движения, и сводка руководителя.

Значения — в `.env` (`SLA_*_HOURS`), а не в коде: у разных компаний
разный ритм, а у одной он меняется от сезона.
"""

from __future__ import annotations

from app.config import get_settings
from app.db.models import RequestStatus

#: Порог «без движения» по умолчанию, часов. Отдельно от нормативов
#: этапа: заявка может укладываться в норматив закупа и всё равно стоять
#: сутки, и руководителю это стоит увидеть.
DEFAULT_STALE_HOURS = 24


def norms() -> dict[RequestStatus, int | None]:
    """Норматив каждого этапа в часах. None — норматива нет.

    Черновик нормативом не ограничен: он у автора, и никто, кроме него,
    его не двигает. Завершённые статусы ждать уже нечего.
    """
    settings = get_settings()
    return {
        RequestStatus.DRAFT: None,
        RequestStatus.PENDING: settings.sla_pending_hours,
        RequestStatus.SOURCING: settings.sla_sourcing_hours,
        RequestStatus.PRICED: settings.sla_priced_hours,
        RequestStatus.APPROVED: settings.sla_approved_hours,
    }


def norm_for(status: RequestStatus) -> int | None:
    return norms().get(status)


def stale_hours() -> int:
    """Со скольких часов заявка считается стоящей без движения."""
    return get_settings().stale_hours
