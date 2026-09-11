"""Количество на складе. Как деньги, только другая точность.

Отдельно от `money.py` намеренно: у денег две цифры после запятой и
округление до копейки, у склада три — кабель метрами, цемент
килограммами. Смешать их в одном модуле значит однажды округлить
2,5 метра до 2,50 сомони.

Показываем без хвостовых нулей: «40», а не «40,000». Три знака нужны
расчёту, а человеку на экране они мешают — он видит сорок мешков.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.core.money import GROUP_SEPARATOR

#: Три знака после запятой. Больше не нужно: склад не взвешивает граммы.
STEP = Decimal("0.001")


def to_quantity(value: str | int | float | Decimal) -> Decimal:
    """Приводит значение к Decimal с тремя знаками.

    float принимается только ради данных из JSON и сразу переводится
    через строку: двоичной погрешности в остатке быть не должно.
    """
    try:
        dec = Decimal(str(value)) if isinstance(value, float) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Не число: {value!r}") from exc
    return dec.quantize(STEP, rounding=ROUND_HALF_UP)


def quantity(value: Decimal) -> str:
    """40.000 → «40», 12.500 → «12,5», 1200.250 → «1 200,25»."""
    dec = to_quantity(value)
    sign = "-" if dec < 0 else ""
    whole, _, frac = format(abs(dec), "f").partition(".")
    frac = frac.rstrip("0")

    groups: list[str] = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)

    head = GROUP_SEPARATOR.join(groups)
    return f"{sign}{head},{frac}" if frac else f"{sign}{head}"


def with_unit(value: Decimal, unit: str | None) -> str:
    """«40 мешков» не собираем: единица пишется как её завели — «40 меш.»."""
    text = quantity(value)
    return f"{text} {unit}".strip() if unit else text
