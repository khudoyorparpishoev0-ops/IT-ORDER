"""Деньги и время — фундамент расчётов, ошибки здесь портят весь табель."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.core.money import money, somoni, to_decimal
from app.core.time import (
    ensure_aware,
    format_local_date,
    local_date,
    month_bounds,
    to_local,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("0"), "0,00"),
        (Decimal("30"), "30,00"),
        (Decimal("150.5"), "150,50"),
        (Decimal("1070"), "1 070,00"),
        (Decimal("18500"), "18 500,00"),
        (Decimal("156000"), "156 000,00"),
        (Decimal("1250000"), "1 250 000,00"),
        (Decimal("-640.25"), "-640,25"),
    ],
)
def test_money_format_ru(value: Decimal, expected: str) -> None:
    assert money(value) == expected.replace(" ", " ")


def test_somoni_adds_word_not_symbol() -> None:
    assert somoni(Decimal("1850")) == "1 850,00 сомони"


def test_float_does_not_leak_binary_error() -> None:
    # 0.1 + 0.2 в float даёт 0.30000000000000004; через строку — ровно 0.30
    assert to_decimal(0.1 + 0.2) == Decimal("0.30")


def test_rounding_is_half_up() -> None:
    assert to_decimal("2.345") == Decimal("2.35")
    assert to_decimal("2.344") == Decimal("2.34")


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValueError):
        ensure_aware(datetime(2026, 9, 4, 18, 12))


def test_local_conversion_uses_company_timezone() -> None:
    # 04.09.2026 20:30 UTC — это уже 5 сентября в Душанбе (UTC+5)
    utc = datetime(2026, 9, 4, 20, 30, tzinfo=timezone.utc)
    assert to_local(utc).hour == 1
    assert local_date(utc).day == 5
    assert format_local_date(utc) == "05.09.2026"


def test_month_bounds_are_half_open() -> None:
    start, end = month_bounds(2026, 9)
    # Сентябрь в Душанбе начинается на 5 часов раньше по UTC
    assert start == datetime(2026, 8, 31, 19, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 9, 30, 19, 0, tzinfo=timezone.utc)
