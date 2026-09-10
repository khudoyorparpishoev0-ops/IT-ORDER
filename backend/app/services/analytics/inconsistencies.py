"""Нестыковки: чего в заявке не хватает или что в ней не сходится.

Всё это находится обычными проверками по базе — модель здесь не нужна и
не участвует. Правило одно: **сообщаем о факте, а не о вине**. «В
описании 5, в количестве 1» — да; «сотрудник ошибся» — нет: может, так и
задумано, и решает это человек, а не программа.

Чего мы намеренно не проверяем: соответствие суммы подтверждающему
документу. Накладных и чеков файлами в ORDER нет — это записано в
`BLIND_SPOTS`. Появятся — проверка добавится сюда же.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.db.models import EventKind, ExpenseRequest, RequestStatus
from app.services.analytics.stale import in_work
from app.services.requests import title_of

#: Слова, которыми считают штуки. Именно они отличают количество от
#: размера и марки: «два мешка» — количество, «45 см» и «М500» — нет.
_COUNTERS = (
    "мешок", "мешка", "мешков", "бухта", "бухты", "бухт", "шт", "штук",
    "штуки", "комплект", "комплекта", "комплектов", "упаковка", "упаковки",
    "упаковок", "паллета", "паллеты", "паллет", "пара", "пары", "пар",
    "рулон", "рулона", "рулонов", "банка", "банки", "банок", "канистра",
    "канистры", "канистр", "ящик", "ящика", "ящиков", "коробка", "коробки",
    "коробок", "пачка", "пачки", "пачек",
)
_WORD_NUMBERS = {
    "один": 1, "одна": 1, "одно": 1, "два": 2, "две": 2, "три": 3,
    "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8,
    "девять": 9, "десять": 10, "двенадцать": 12, "двадцать": 20,
}
_COUNTER_RE = "|".join(_COUNTERS)
#: «2 мешка», «два мешка» — и только в начале описания. Число в середине
#: почти всегда характеристика: «Кабель ВВГ 3×2,5», «Шпатель 45 см».
_QUANTITY = re.compile(
    rf"^\s*(?:(\d{{1,4}})|({'|'.join(_WORD_NUMBERS)}))\s+(?:{_COUNTER_RE})\b"
)

#: Сколько возвратов на доработку уже перебор. Возврат в ORDER — это
#: отклонение с последующей новой заявкой, поэтому считаем отклонения.
RETURNS_LIMIT = 2


@dataclass(frozen=True)
class Issue:
    """Найденная нестыковка. Решение — за человеком."""

    request_id: int
    number: str
    title: str
    project: str
    employee: str
    #: critical | warning | info
    severity: str
    code: str
    #: Человеческое объяснение: что именно не сходится.
    detail: str


def _quantity_in_text(text: str) -> int | None:
    """Количество, названное прямо в описании позиции. None — не названо.

    Правило намеренно узкое: число считается количеством, только если оно
    стоит в начале и за ним идёт счётное слово — «2 мешка», «два мешка».
    Всё остальное количеством не является: «Шпатель 45 см» — это размер,
    «Цемент М500» — марка, «Кабель ВВГ 3×2,5» — сечение.

    Широкое правило мы попробовали и выбросили: на демо-данных оно
    поймало четыре «нестыковки», и все четыре оказались выдумкой.
    Предупреждение, которое чаще неверно, чем верно, учит людей
    игнорировать все предупреждения подряд — включая настоящие.
    """
    low = " ".join((text or "").lower().replace("ё", "е").split())
    found = _QUANTITY.match(low)
    if found is None:
        return None
    digits, word = found.group(1), found.group(2)
    return int(digits) if digits else _WORD_NUMBERS[word]


def check_request(
    request: ExpenseRequest, *, rejected_before: int = 0
) -> list[Issue]:
    """Все нестыковки одной заявки."""
    issues: list[Issue] = []

    def add(severity: str, code: str, detail: str) -> None:
        issues.append(
            Issue(
                request_id=request.id,
                number=request.number,
                title=title_of(request),
                project=request.project.name if request.project else "—",
                employee=request.employee.full_name if request.employee else "—",
                severity=severity,
                code=code,
                detail=detail,
            )
        )

    if not request.lines:
        add("critical", "no_lines", "В заявке нет ни одной позиции")

    for line in request.lines:
        said = _quantity_in_text(line.title)
        if said is not None and said != line.quantity:
            add(
                "warning",
                "quantity_mismatch",
                f"«{line.title}»: в описании {said}, в поле количества {line.quantity}",
            )
        if not (line.unit or "").strip():
            add(
                "info",
                "no_unit",
                f"«{line.title}»: не указана единица измерения — закупу придётся уточнять",
            )

    if request.project_id is None:
        add("critical", "no_project", "Не указан объект")
    if request.category is None:
        add("info", "no_category", "Не указана категория расхода")

    # Отклонение без объяснения — тупик: автор не знает, что исправлять.
    if request.status is RequestStatus.REJECTED and not (
        request.decision_comment or ""
    ).strip():
        add("critical", "reject_without_reason", "Отклонена без комментария")

    if request.status is RequestStatus.PRICED and not (
        request.sourcing_comment or ""
    ).strip():
        priced = [line for line in request.lines if line.price is not None]
        if not priced:
            add(
                "warning",
                "priced_without_prices",
                "Закуп отметил заявку оценённой, но цен в ней нет",
            )

    if rejected_before >= RETURNS_LIMIT:
        add(
            "warning",
            "repeated_returns",
            f"У автора {rejected_before} отклонённых заявок по этому объекту — "
            "возможно, требование сформулировано неясно",
        )

    return issues


def find_all(
    session: Session,
    *,
    now: datetime | None = None,
    rows: list[ExpenseRequest] | None = None,
) -> list[Issue]:
    """Нестыковки во всех незакрытых заявках, самые важные сверху."""
    moment = now or utcnow()
    del moment  # время здесь ни на что не влияет; параметр для единообразия

    issues: list[Issue] = []
    for request in rows if rows is not None else in_work(session):
        issues.extend(check_request(request))

    order = {"critical": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (order.get(i.severity, 3), i.number))
    return issues
