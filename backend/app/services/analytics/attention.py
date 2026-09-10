"""Единая очередь «требует внимания».

Одна функция вместо пяти списков: просрочки, застой, нестыковки, дубли и
необычные суммы приходят к руководителю не по отдельности, а одной
очередью — иначе он читает пять экранов и складывает их в голове.

Заявка попадает сюда один раз, даже если у неё несколько причин: две
строки об одной заявке — это не два дела, а одно.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.services.analytics import inconsistencies as inc
from app.services.analytics import stale
from app.services.analytics.facts import find_duplicates
from app.services.analytics.scope import Scope
from app.services.requests import title_of

#: Порядок разбора. Критичное — сверху, справочное — вниз.
ORDER = {"critical": 0, "warning": 1, "info": 2}

#: Сколько строк отдаём. Очередь длиннее тридцати не разбирают, её
#: закрывают; детали живут за кнопкой «посмотреть все».
LIMIT = 30


@dataclass(frozen=True)
class Item:
    """Заявка, требующая внимания, и все причины разом."""

    request_id: int
    number: str
    title: str
    project: str
    employee: str
    status: str
    stage_label: str
    hours_in_status: int
    norm_hours: int | None
    amount: Decimal
    priced: bool
    severity: str
    #: Почему она здесь: «стоит 31 ч при нормативе 8 ч», «возможный дубль».
    reasons: list[str] = field(default_factory=list)
    #: Коды причин для панели и фильтров: overdue, stuck, duplicate…
    codes: list[str] = field(default_factory=list)


def requires_attention(
    session: Session,
    *,
    now: datetime | None = None,
    limit: int = LIMIT,
    scope: Scope | None = None,
) -> list[Item]:
    """Всё, что требует внимания руководителя, одной очередью.

    Считает база. Модель этот список не строит и не дополняет — она
    только пересказывает его словами.
    """
    moment = now or utcnow()
    rows = stale.in_work(session, scope=scope)
    by_id = {r.id: r for r in rows}

    reasons: dict[int, list[str]] = {}
    codes: dict[int, list[str]] = {}
    severity: dict[int, str] = {}
    stage: dict[int, tuple[str, int, int | None]] = {}

    def note(request_id: int, code: str, reason: str, level: str) -> None:
        reasons.setdefault(request_id, []).append(reason)
        codes.setdefault(request_id, []).append(code)
        current = severity.get(request_id)
        if current is None or ORDER[level] < ORDER[current]:
            severity[request_id] = level

    for item in stale.stuck_requests(session, now=moment, rows=rows):
        stage[item.request_id] = (item.stage_label, item.hours_in_status, item.norm_hours)
        note(
            item.request_id,
            "overdue" if item.overdue else "stuck",
            item.reason,
            item.severity,
        )

    for issue in inc.find_all(session, rows=rows):
        if issue.severity == "info":
            # Справочное замечание само по себе внимания не требует: оно
            # дополняет заявку, которая и так в очереди.
            if issue.request_id in reasons:
                note(issue.request_id, issue.code, issue.detail, "info")
            continue
        note(issue.request_id, issue.code, issue.detail, issue.severity)

    for pair in find_duplicates(session, now=moment):
        detail = (
            f"похожа на {pair.second_number} — "
            f"{', '.join(pair.materials[:3])}"
        )
        note(pair.first_id, "duplicate", detail, "info")
        note(
            pair.second_id,
            "duplicate",
            f"похожа на {pair.first_number} — {', '.join(pair.materials[:3])}",
            "info",
        )

    items: list[Item] = []
    for request_id, level in severity.items():
        request = by_id.get(request_id)
        if request is None:
            continue
        stage_label, hours, norm = stage.get(
            request_id, (request.status.value, 0, None)
        )
        items.append(
            Item(
                request_id=request.id,
                number=request.number,
                title=title_of(request),
                project=request.project.name,
                employee=request.employee.full_name,
                status=request.status.value,
                stage_label=stage_label,
                hours_in_status=hours,
                norm_hours=norm,
                amount=request.amount,
                priced=any(line.price is not None for line in request.lines),
                severity=level,
                reasons=reasons.get(request_id, []),
                codes=sorted(set(codes.get(request_id, []))),
            )
        )

    items.sort(key=lambda i: (ORDER[i.severity], -i.hours_in_status))
    return items[:limit]
