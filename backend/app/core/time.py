"""Работа со временем. В базе только UTC, бизнес-логика — в поясе компании.

Naive datetime запрещены: любая попытка их использовать поднимает ошибку,
иначе расхождение всплывает через месяцы в неверном табеле.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_timezone)


def utcnow() -> datetime:
    """Текущий момент в UTC, всегда с таймзоной."""
    return datetime.now(timezone.utc)


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Ожидался datetime с таймзоной, получен naive")
    return value


def to_local(value: datetime) -> datetime:
    """UTC → местное время компании."""
    return ensure_aware(value).astimezone(_tz())


def local_date(value: datetime) -> date:
    """Дата события в местном поясе, а не в UTC."""
    return to_local(value).date()


def local_day_bounds(day: date) -> tuple[datetime, datetime]:
    """Границы местных суток в UTC. Интервал полуоткрытый: [начало, начало
    следующего дня), поэтому события последней секунды не теряются."""
    tz = _tz()
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """Границы местного календарного месяца в UTC."""
    tz = _tz()
    start = datetime(year, month, 1, tzinfo=tz)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        end = datetime(year, month + 1, 1, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def format_local_date(value: datetime) -> str:
    """Дата в формате макета: 04.09.2026."""
    return to_local(value).strftime("%d.%m.%Y")


def format_local_datetime(value: datetime) -> str:
    """Метка истории: 04.09.2026, 18:12."""
    return to_local(value).strftime("%d.%m.%Y, %H:%M")
