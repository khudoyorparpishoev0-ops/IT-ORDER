"""Директорский режим бота: аналитика в Telegram.

Отдельной аналитики для бота нет и не будет. Всё, что он показывает,
считает тот же `services/analytics/`, что и панель: сводка, очередь
внимания, застой, просрочки, объекты. Второй набор расчётов однажды
разошёлся бы с первым, и никто не понял бы, какая цифра настоящая.

Права те же и берутся из той же точки (`analytics/scope.py`). Роль
перечитывается из базы на каждом нажатии: разговор мог начаться вчера, а
права с тех пор изменились.

Ограничение Telegram — 4096 символов на сообщение. Поэтому длинные
списки не отправляются целиком: очередь идёт страницами по пять, а
текст на всякий случай подрезается.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from sqlalchemy.orm import Session

from app.core.text import plural
from app.core.time import utcnow
from app.db.models import AiSource, Employee
from app.services import intelligence
from app.services.analytics import anomalies, attention, digest, executive, scope, stale
from app.services.analytics.facts import project_stats
from app.services.audit import write_audit
from app.services.notifications import panel_url

log = logging.getLogger(__name__)

#: Кнопки директорского блока.
DIR_OVERVIEW = "dir:overview"
DIR_ATTENTION = "dir:att"
DIR_STUCK = "dir:stuck"
DIR_OVERDUE = "dir:over"
DIR_PROJECTS = "dir:proj"
DIR_ASK = "dir:ask"
DIR_MORNING = "dir:morning"
DIR_EVENING = "dir:evening"
#: Страница очереди: `dir:page:att:2`.
DIR_PAGE = "dir:page:"
#: Оценка ответа AI: `dir:rate:1:42` — полезно/нет и номер обращения.
DIR_RATE = "dir:rate:"

#: Сколько заявок на странице. Пять читаются с телефона одним взглядом;
#: десять уже листают, а двадцать закрывают не читая.
PAGE_SIZE = 5

#: Запас до предела Telegram (4096). Режем раньше: у сообщения есть ещё
#: разметка и кнопки, и упереться в предел на боевом сервере — значит
#: молча не отправить ничего.
MAX_TEXT = 3500

#: Точка и слово: цвет в Telegram передать нечем, но уровень назвать надо.
MARK = {"critical": "!!", "warning": "!", "info": "·"}

NO_ACCESS = (
    "Аналитика доступна руководителю, бухгалтерии и администратору. "
    "Если это ошибка — напишите администратору системы."
)
AI_OFF = (
    "Помощник сейчас недоступен, но цифры на месте: нажмите «Сводка» или "
    "«Требуют внимания»."
)
AI_UNSURE = (
    "Не удалось точно определить запрос. Могу показать общую сводку, "
    "просроченные заявки или заявки без движения."
)


@dataclass
class Reply:
    """Ответ бота: текст, кнопки выбора и, может быть, ссылка."""

    text: str
    choices: list[tuple[str, str]] = field(default_factory=list)
    button: tuple[str, str] | None = None


def _cut(text: str) -> str:
    """Подрезает сообщение до предела Telegram."""
    if len(text) <= MAX_TEXT:
        return text
    return text[: MAX_TEXT - 1] + "…"


def _link(label: str, path: str) -> str:
    """Номер заявки ссылкой на её карточку.

    Ссылка обычная, без токенов и секретов: человек открывает панель под
    своей сессией, и если он не вошёл — увидит экран входа на том же
    адресе. Без `PUBLIC_BASE_URL` вести некуда, и тогда остаётся просто
    жирный номер: относительный адрес Telegram ссылкой не сделает.
    """
    url = panel_url(path)
    if not url.startswith("http"):
        return "<b>" + label + "</b>"
    return '<a href="' + url + '">' + label + "</a>"


def available(employee: Employee) -> bool:
    """Показывать ли этому человеку директорский блок."""
    return scope.can_see_analytics(employee)


def menu_rows(employee: Employee) -> list[tuple[str, str]]:
    """Кнопки директорского блока. Пусто — человеку они не положены."""
    if not available(employee):
        return []
    return [
        ("Сводка", DIR_OVERVIEW),
        ("Требуют внимания", DIR_ATTENTION),
        ("Без движения", DIR_STUCK),
        ("Просроченные", DIR_OVERDUE),
        ("Объекты", DIR_PROJECTS),
        ("Спросить ORDER AI", DIR_ASK),
    ]


def _audit(
    session: Session,
    employee: Employee,
    *,
    intent: str,
    found: int,
    with_ai: bool,
    latency_ms: int | None = None,
) -> None:
    """След директорского запроса из бота.

    Кто, что спросил, сколько нашлось, звали ли модель и сколько ждали.
    Ни промпта, ни ответа модели: журнал отвечает на вопрос «кто
    смотрел», а не хранит копию отчёта.
    """
    parts = [f"telegram · {intent} · {found}", "с AI" if with_ai else "без AI"]
    if latency_ms is not None:
        parts.append(f"{latency_ms} мс")
    write_audit(
        session,
        entity="analytics",
        entity_id=intent,
        action="ai_question" if with_ai else "analytics_view",
        employee=employee,
        details=" · ".join(parts),
    )


# --- Сводка -------------------------------------------------------------------


def overview(session: Session, employee: Employee) -> Reply:
    """Краткая сводка руководителя. Без списка заявок: он за кнопкой."""
    if not available(employee):
        return Reply(NO_ACCESS)

    box = scope.for_employee(employee)
    data = executive.overview(session, scope=box)
    _audit(session, employee, intent="overview", found=data.requires_attention, with_ai=False)

    lines = [
        "<b>ORDER Intelligence</b>",
        "",
        f"Активные: {data.active_requests}",
        f"Создано сегодня: {data.created_today}",
        f"Выполнено сегодня: {data.completed_today}",
        f"Просрочено: {data.overdue}",
        f"Без движения: {data.stuck}",
        f"Требуют внимания: {data.requires_attention}",
    ]
    if data.problems:
        lines.append("")
        lines.append("<b>Основные проблемы</b>")
        lines.extend(
            f"{i}. {p.count} {p.label}" for i, p in enumerate(data.problems, 1)
        )
    else:
        lines.append("")
        lines.append("Всё в срок, разбирать нечего.")

    return Reply(
        _cut("\n".join(lines)),
        choices=[("Требуют внимания", DIR_ATTENTION)] if data.requires_attention else [],
        button=("Открыть ORDER", panel_url("/intelligence")),
    )


# --- Списки страницами ----------------------------------------------------------


def _page_of(items: list, page: int) -> tuple[list, int, int]:
    """Страница списка: элементы, номер страницы и всего страниц."""
    total = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total - 1))
    start = page * PAGE_SIZE
    return items[start : start + PAGE_SIZE], page, total


def _nav(kind: str, page: int, total: int) -> list[tuple[str, str]]:
    """Кнопки перелистывания. Одна страница — кнопок нет."""
    if total <= 1:
        return []
    rows = []
    if page > 0:
        rows.append(("Назад", f"{DIR_PAGE}{kind}:{page - 1}"))
    if page < total - 1:
        rows.append((f"Следующие ({page + 2} из {total})", f"{DIR_PAGE}{kind}:{page + 1}"))
    return rows


def attention_page(session: Session, employee: Employee, page: int = 0) -> Reply:
    """Очередь внимания страницами. Важное сверху."""
    if not available(employee):
        return Reply(NO_ACCESS)

    box = scope.for_employee(employee)
    items = attention.requires_attention(session, scope=box)
    _audit(session, employee, intent="attention", found=len(items), with_ai=False)
    if not items:
        return Reply("Разбирать нечего: всё в срок.")

    shown, page, total = _page_of(items, page)
    lines = [f"<b>Требуют внимания: {len(items)}</b>", ""]
    for item in shown:
        lines.append(
            f"{MARK.get(item.severity, '·')} "
            f"{_link(item.number, f'/requests/{item.request_id}')} · {item.project}\n"
            f"{item.stage_label}\n"
            f"{'; '.join(item.reasons[:2])}\n"
        )
    return Reply(
        _cut("\n".join(lines)),
        choices=_nav("att", page, total),
        button=("Открыть в ORDER", panel_url("/intelligence")),
    )


def stuck_page(session: Session, employee: Employee, page: int = 0) -> Reply:
    """Заявки без движения — те, где норматив ещё не нарушен."""
    return _stale_page(session, employee, page, overdue=False)


def overdue_page(session: Session, employee: Employee, page: int = 0) -> Reply:
    """Заявки, вышедшие за норматив своего этапа."""
    return _stale_page(session, employee, page, overdue=True)


def _stale_page(
    session: Session, employee: Employee, page: int, *, overdue: bool
) -> Reply:
    if not available(employee):
        return Reply(NO_ACCESS)

    box = scope.for_employee(employee)
    rows = stale.stuck_requests(session, scope=box)
    items = [r for r in rows if r.overdue is overdue]
    kind = "over" if overdue else "stuck"
    _audit(
        session,
        employee,
        intent="overdue" if overdue else "stuck",
        found=len(items),
        with_ai=False,
    )
    if not items:
        return Reply(
            "Просроченных нет." if overdue else "Всё движется: застоя нет."
        )

    shown, page, total = _page_of(items, page)
    head = "Просроченные" if overdue else "Без движения"
    lines = [f"<b>{head}: {len(items)}</b>", ""]
    for item in shown:
        lines.append(
            f"{MARK.get(item.severity, '·')} "
            f"{_link(item.number, f'/requests/{item.request_id}')} · {item.project}\n"
            f"{item.assignee}\n"
            f"{item.reason}\n"
        )
    return Reply(
        _cut("\n".join(lines)),
        choices=_nav(kind, page, total),
        button=("Открыть в ORDER", panel_url("/intelligence")),
    )


def projects(session: Session, employee: Employee) -> Reply:
    """Объекты: заявки, расход и задержки. Самые проблемные сверху."""
    if not available(employee):
        return Reply(NO_ACCESS)

    stats = project_stats(session)
    _audit(session, employee, intent="project_summary", found=len(stats), with_ai=False)
    if not stats:
        return Reply("Объектов с заявками пока нет.")

    ordered = sorted(stats, key=lambda p: (-p.over_norm, -p.active_count))[:PAGE_SIZE]
    lines = ["<b>Объекты</b>", ""]
    for item in ordered:
        note = (
            f", за нормативом {item.over_norm}"
            if item.over_norm
            else ""
        )
        lines.append(
            f"<b>{item.name}</b>\n"
            f"в работе {item.active_count}{note}\n"
            f"за месяц {item.month_count} "
            f"{plural(item.month_count, 'заявка', 'заявки', 'заявок')}, "
            f"{item.month_amount} сомони\n"
        )
    return Reply(
        _cut("\n".join(lines)),
        button=("Открыть отчёты", panel_url("/reports")),
    )


# --- Сводки за период -------------------------------------------------------------


def digest_reply(session: Session, employee: Employee, kind: str) -> Reply:
    """Утренняя или вечерняя сводка по запросу.

    По запросу, а не по расписанию: автоматическая рассылка — отдельная
    работа, и включать её раньше, чем формат устоялся, значит будить
    людей черновиком.
    """
    if not available(employee):
        return Reply(NO_ACCESS)

    box = scope.for_employee(employee)
    data = (
        digest.evening(session, scope=box)
        if kind == "evening"
        else digest.morning(session, scope=box)
    )
    _audit(
        session,
        employee,
        intent=f"digest_{data.kind}",
        found=len(data.problems),
        with_ai=False,
    )
    return Reply(
        _cut(digest.as_text(data)),
        button=("Открыть ORDER", panel_url("/intelligence")),
    )


# --- Вопрос руководителя ----------------------------------------------------------


def ask(session: Session, employee: Employee, question: str) -> Reply:
    """Вопрос обычными словами. Тот же реестр намерений, что и в панели.

    Модель называет намерение, сервер выполняет разрешённую функцию,
    модель пересказывает результат. SQL она не пишет и базы не видит.
    """
    if not available(employee):
        return Reply(NO_ACCESS)

    box = scope.for_employee(employee)
    started = utcnow()
    reply = intelligence.ask_by_intent(
        session,
        question=question,
        scope=box,
        source=AiSource.TELEGRAM,
    )
    latency = int((utcnow() - started).total_seconds() * 1000)
    _audit(
        session,
        employee,
        intent=reply.intent or "ask",
        found=len(reply.requests),
        with_ai=True,
        latency_ms=latency,
    )

    if not reply.enabled:
        return Reply(AI_OFF, choices=[("Сводка", DIR_OVERVIEW)])
    if not reply.available:
        # Классификация или ответ не удались — не тупик: предлагаем то,
        # что считает база и что работает всегда.
        return Reply(
            AI_UNSURE,
            choices=[
                ("Сводка", DIR_OVERVIEW),
                ("Просроченные", DIR_OVERDUE),
                ("Без движения", DIR_STUCK),
            ],
        )

    lines = [reply.answer]
    if reply.bullets:
        lines.append("")
        lines.extend(f"• {b}" for b in reply.bullets)
    if reply.requests:
        lines.append("")
        for ref in reply.requests[:3]:
            lines.append(f"{_link(ref.number, f'/requests/{ref.id}')} — {ref.why}")
    if reply.recommendations:
        lines.append("")
        lines.append("<b>Что стоит проверить</b>")
        lines.extend(f"• {r}" for r in reply.recommendations)

    # Оценку показываем только под ответом модели: под обычной сводкой
    # оценивать нечего — там цифры базы, а не мнение.
    choices: list[tuple[str, str]] = []
    if reply.interaction_id is not None:
        choices = [
            ("Полезно", f"{DIR_RATE}1:{reply.interaction_id}"),
            ("Не подходит", f"{DIR_RATE}0:{reply.interaction_id}"),
        ]
    return Reply(_cut("\n".join(lines)), choices=choices)


def rate(session: Session, employee: Employee, useful: bool, interaction_id: int) -> Reply:
    """Оценка ответа помощника из бота."""
    from app.core.errors import NotFoundError
    from app.services import ai_feedback

    try:
        ai_feedback.rate(
            session, employee, interaction_id=interaction_id, useful=useful
        )
    except NotFoundError:
        return Reply("Этот ответ уже не найти — оценка не сохранилась.")
    return Reply("Спасибо, учтём." if useful else "Спасибо, разберёмся.")


def ask_prompt() -> Reply:
    """Приглашение задать вопрос с готовыми примерами."""
    return Reply(
        "Спросите обычными словами. Например:\n\n"
        "• Что сейчас требует моего внимания?\n"
        "• Какие заявки зависли?\n"
        "• Где превышен норматив?\n"
        "• Что изменилось за неделю?\n"
        "• Какие объекты самые проблемные?"
    )


def deviations(session: Session, employee: Employee) -> Reply:
    """Что отличается от обычного уровня. Не нарушение — отклонение."""
    if not available(employee):
        return Reply(NO_ACCESS)
    found = anomalies.find(session)
    _audit(session, employee, intent="compare_periods", found=len(found), with_ai=False)
    if not found:
        return Reply("Показатели на обычном уровне.")
    lines = ["<b>Отличается от обычного уровня</b>", ""]
    lines.extend(f"{MARK.get(a.severity, '·')} {a.detail}" for a in found)
    return Reply(_cut("\n".join(lines)))
