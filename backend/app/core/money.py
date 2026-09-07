"""Деньги. Только Decimal — float для сумм запрещён.

Формат вывода — ru-RU: разделитель разрядов неразрывный пробел,
копейки через запятую (1 250 000,00). Знак валюты в число не входит:
валюта указывается в заголовке столбца или словом «сомони».
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

#: Узкий неразрывный пробел ломает вёрстку в Excel, поэтому берём обычный
#: неразрывный — он не даёт числу переноситься по разрядам.
GROUP_SEPARATOR = " "
CENTS = Decimal("0.01")


def to_decimal(value: str | int | float | Decimal) -> Decimal:
    """Приводит значение к Decimal с двумя знаками.

    float принимается только ради данных из JSON и сразу переводится через
    строку, чтобы не тащить двоичную погрешность в сумму заявки.
    """
    try:
        if isinstance(value, float):
            dec = Decimal(str(value))
        else:
            dec = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Не число: {value!r}") from exc
    return dec.quantize(CENTS, rounding=ROUND_HALF_UP)


def money(value: Decimal) -> str:
    """1250000 → «1 250 000,00»."""
    quantized = to_decimal(value)
    sign = "-" if quantized < 0 else ""
    whole, _, frac = format(abs(quantized), "f").partition(".")
    frac = (frac + "00")[:2]

    groups: list[str] = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)

    return f"{sign}{GROUP_SEPARATOR.join(groups)},{frac}"


def somoni(value: Decimal) -> str:
    """Сумма со словом «сомони» — для текста, не для колонок таблиц."""
    return f"{money(value)} сомони"
