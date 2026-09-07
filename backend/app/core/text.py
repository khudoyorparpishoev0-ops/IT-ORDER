"""Русский текст в отчётах и подписях.

Числительные склоняются: «1 выплата», «2 выплаты», «5 выплат». Без этого
в отчёте, который читает руководство, получается «2 выплат».
"""

from __future__ import annotations


def plural(number: int, one: str, few: str, many: str) -> str:
    """Форма слова при числе: (1, 2, 5) → (one, few, many)."""
    mod10 = abs(number) % 10
    mod100 = abs(number) % 100
    if mod10 == 1 and mod100 != 11:
        return one
    if 2 <= mod10 <= 4 and not 12 <= mod100 <= 14:
        return few
    return many


def count_with_word(number: int, one: str, few: str, many: str) -> str:
    """«2 выплаты», «5 заявок»."""
    return f"{number} {plural(number, one, few, many)}"


def days(number: int) -> str:
    """«1 день», «3 дня», «7 дней»."""
    return count_with_word(number, "день", "дня", "дней")
