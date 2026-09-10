"""Кому и когда уходят автоматические сводки ORDER Intelligence.

Что здесь есть: получатели, их местное время, проверка права в момент
отправки, сборка текста и решение «слать или промолчать».

Чего здесь нет: расчётов. Все числа приходят из `services/analytics/` —
того же, что отвечает панели и боту. Второй набор расчётов «специально
для рассылки» однажды разошёлся бы с первым, и цифра в утреннем
сообщении перестала бы совпадать с цифрой на экране.

Главное правило этого модуля: **сводка должна быть полезной, а не
приходить.** Поэтому пустая вечерняя сводка по умолчанию не
отправляется, один и тот же сигнал не повторяется чаще, чем раз в
`CRITICAL_ALERT_REPEAT_HOURS`, а «всё починилось» не шлётся отдельным
сообщением вовсе.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ValidationError
from app.core.text import plural
from app.core.time import utcnow
from app.db.models import Employee, IntelligenceDelivery, IntelligenceKind
from app.services.analytics import attention, digest, executive, scope
from app.services.notifications import dedup, delivery
from app.services.notifications.requests import panel_url

log = logging.getLogger(__name__)

#: Сколько проблем перечисляем поимённо. Список из пятнадцати строк в
#: сообщении не читают — по нему пробегают глазами и закрывают.
TOP_PROBLEMS = 3

#: Сколько элементов уходит модели на объяснение. Сотни заявок ей не
#: нужны: она пересказывает первые несколько, а платить пришлось бы за
#: все — и за каждую утреннюю рассылку каждого руководителя.
AI_CONTEXT_LIMIT = 10


@dataclass(frozen=True)
class Prepared:
    """Готовое сообщение и то, что о нём нужно знать истории доставок."""

    text: str
    result_count: int
    ai_used: bool
    button: tuple[str, str] | None = None
    #: Отправлять ли вообще. False — разбирать нечего, и человек просил
    #: в таком случае его не трогать.
    worth_sending: bool = True


# --- Получатели и их время -----------------------------------------------------


def timezone_of(employee: Employee) -> ZoneInfo:
    """Пояс человека. Не задан или неизвестен — корпоративный.

    Неизвестный пояс — не повод не отправить сводку: человек мог
    ошибиться в названии, а рассылка от этого страдать не должна.
    """
    name = (employee.timezone or "").strip() or get_settings().app_timezone
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("Неизвестный пояс %r у сотрудника %s", name, employee.id)
        return ZoneInfo(get_settings().app_timezone)


def local_now(employee: Employee, now: datetime | None = None) -> datetime:
    return (now or utcnow()).astimezone(timezone_of(employee))


def subscribers(session: Session) -> list[Employee]:
    """Кто подписан на сводки. Право здесь ещё не проверяется."""
    return list(
        session.scalars(
            select(Employee).where(
                Employee.active.is_(True),
                Employee.intelligence_enabled.is_(True),
            )
        )
    )


def may_receive(employee: Employee) -> bool:
    """Можно ли этому человеку отправлять аналитику ПРЯМО СЕЙЧАС.

    Право проверяется в момент отправки, а не при подписке: роль могли
    понизить месяц назад, а настройка осталась. Старая настройка правом
    доступа не является — иначе разжалованный руководитель продолжал бы
    получать цифры по всей компании.
    """
    return scope.can_see_analytics(employee) and delivery.can_deliver(employee)


def _due(local: datetime, at: time) -> bool:
    """Наступило ли время у этого человека сегодня."""
    return local.time() >= at


def due_now(
    employee: Employee, kind: IntelligenceKind, now: datetime | None = None
) -> bool:
    """Пора ли отправлять этот вид сводки."""
    local = local_now(employee, now)
    if kind is IntelligenceKind.MORNING:
        return employee.digest_morning_enabled and _due(local, employee.digest_morning_time)
    if kind is IntelligenceKind.EVENING:
        return employee.digest_evening_enabled and _due(local, employee.digest_evening_time)
    return False


def local_date_of(employee: Employee, now: datetime | None = None) -> date:
    return local_now(employee, now).date()


# --- Настройки подписки -----------------------------------------------------------


def describe(session: Session, employee: Employee) -> dict:
    """Настройки рассылки для панели и для бота.

    Одна функция на оба: в боте настройки только показываются, и текст
    там не должен разойтись с тем, что человек видит в «Параметрах».
    """
    settings = get_settings()
    return {
        "enabled": employee.intelligence_enabled,
        "morning_enabled": employee.digest_morning_enabled,
        "evening_enabled": employee.digest_evening_enabled,
        "morning_time": employee.digest_morning_time.strftime("%H:%M"),
        "evening_time": employee.digest_evening_time.strftime("%H:%M"),
        "critical_alerts_enabled": employee.critical_alerts_enabled,
        "when_no_changes": employee.digest_when_no_changes,
        "timezone": employee.timezone,
        "timezone_hint": settings.app_timezone,
        "telegram_connected": delivery.can_deliver(employee),
        "repeat_hours": settings.critical_alert_repeat_hours,
    }


def _parse_time(value: str) -> time:
    hour, _, minute = value.partition(":")
    try:
        return time(int(hour), int(minute))
    except ValueError as exc:
        raise ValidationError(f"Неверное время: {value}") from exc


def update(session: Session, employee: Employee, changes: dict) -> dict:
    """Меняет настройки. Пустой пояс означает «корпоративный».

    Неизвестный пояс отклоняем здесь, а не при отправке: человек видит
    ошибку сразу, пока помнит, что вводил. При отправке проверять поздно —
    там остаётся только подставить корпоративный и записать в лог.
    """
    fields = {
        "enabled": "intelligence_enabled",
        "morning_enabled": "digest_morning_enabled",
        "evening_enabled": "digest_evening_enabled",
        "critical_alerts_enabled": "critical_alerts_enabled",
        "when_no_changes": "digest_when_no_changes",
    }
    for key, column in fields.items():
        if changes.get(key) is not None:
            setattr(employee, column, bool(changes[key]))

    if changes.get("morning_time") is not None:
        employee.digest_morning_time = _parse_time(changes["morning_time"])
    if changes.get("evening_time") is not None:
        employee.digest_evening_time = _parse_time(changes["evening_time"])

    if "timezone" in changes:
        name = (changes["timezone"] or "").strip()
        if name:
            try:
                ZoneInfo(name)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValidationError(f"Неизвестный часовой пояс: {name}") from exc
        employee.timezone = name or None

    session.flush()
    return describe(session, employee)


# --- Сборка сообщений -------------------------------------------------------------


def _ai_summary(session: Session, data, queue) -> tuple[list[str], bool]:
    """Короткое объяснение от модели. Пусто — обошлись без неё.

    Сводку молчание модели не отменяет: цифры уже собраны, и человеку
    они нужнее объяснения. Модель получает компактный набор фактов, а не
    сотни заявок.
    """
    from app.db.models import AiSource
    from app.services import intelligence as brain

    text = brain.explain_overview(
        session, data, queue[:AI_CONTEXT_LIMIT], [], source=AiSource.SCHEDULER
    )
    if not text.available:
        return [], False
    lines = [line for line in ([text.headline] + list(text.summary)) if line]
    return lines[:4], True


def morning(
    session: Session, employee: Employee, *, now: datetime | None = None, use_ai: bool = True
) -> Prepared:
    """Утренняя сводка: что есть сейчас и с чего начинать день."""
    moment = now or utcnow()
    box = scope.for_employee(employee)
    data = executive.overview(session, now=moment, scope=box)
    queue = attention.requires_attention(session, now=moment, scope=box)

    lines = [
        "<b>ORDER Intelligence • Утро</b>",
        "",
        f"Активные: {data.active_requests}",
        f"Новые за вчера: {digest.created_yesterday(session, moment)}",
        f"Просрочено: {data.overdue}",
        f"Без движения: {data.stuck}",
        f"Требуют внимания: {data.requires_attention}",
    ]

    ai_lines, ai_used = ([], False)
    if use_ai and queue:
        ai_lines, ai_used = _ai_summary(session, data, queue)
    if ai_lines:
        lines.append("")
        lines.extend(ai_lines)

    if queue:
        lines.append("")
        lines.append("<b>Главное сегодня</b>")
        for i, item in enumerate(queue[:TOP_PROBLEMS], 1):
            lines.append(
                f"{i}. {_link(item.number, item.request_id)} — {item.reasons[0]}"
            )
        worst = _worst_project(queue)
        if worst:
            name, count = worst
            lines.append("")
            lines.append(
                f"Больше всего проблем на объекте «{name}»: "
                f"{count} {plural(count, 'заявка', 'заявки', 'заявок')}."
            )
    else:
        lines.append("")
        lines.append("Разбирать нечего: всё в срок.")

    return Prepared(
        text="\n".join(lines),
        result_count=len(queue),
        ai_used=ai_used,
        button=("Открыть ORDER", panel_url("/intelligence")),
        # Утро отправляем всегда, если человек его включил: «сегодня всё
        # спокойно» — это тоже ответ на вопрос, с которого он начинает
        # день. Пустоту отсекает только вечерняя сводка.
        worth_sending=True,
    )


def evening(
    session: Session, employee: Employee, *, now: datetime | None = None, use_ai: bool = True
) -> Prepared:
    """Вечерняя сводка: что сделали за день и что остаётся на завтра."""
    moment = now or utcnow()
    box = scope.for_employee(employee)
    data = executive.overview(session, now=moment, scope=box)
    queue = attention.requires_attention(session, now=moment, scope=box)
    delta = digest.overdue_delta(session, now=moment)
    resolved_alerts = dedup.resolved_today(session, employee, now=moment)

    nothing_happened = (
        data.created_today == 0
        and data.completed_today == 0
        and delta["new"] == 0
        and not queue
    )

    lines = [
        "<b>ORDER Intelligence • Итоги дня</b>",
        "",
        f"Создано сегодня: {data.created_today}",
        f"Выполнено: {data.completed_today}",
        f"Активных осталось: {data.active_requests}",
        f"Новых просрочек: {delta['new']}",
        "",
        "<b>С утра</b>",
        f"Устранено: {delta['resolved'] + resolved_alerts}",
        f"Осталось: {delta['left']}",
        f"Новых проблем: {delta['new']}",
    ]

    ai_lines, ai_used = ([], False)
    if use_ai and queue:
        ai_lines, ai_used = _ai_summary(session, data, queue)
    if ai_lines:
        lines.append("")
        lines.extend(ai_lines)

    if queue:
        lines.append("")
        lines.append("<b>На завтра обратить внимание</b>")
        for i, item in enumerate(queue[:TOP_PROBLEMS], 1):
            lines.append(
                f"{i}. {_link(item.number, item.request_id)} — {item.reasons[0]}"
            )

    if nothing_happened:
        return Prepared(
            text="ORDER: критических изменений за день нет.",
            result_count=0,
            ai_used=False,
            worth_sending=employee.digest_when_no_changes,
        )

    return Prepared(
        text="\n".join(lines),
        result_count=len(queue),
        ai_used=ai_used,
        button=("Открыть ORDER", panel_url("/intelligence")),
    )


def _worst_project(queue) -> tuple[str, int] | None:
    """Объект, на котором проблем больше всего."""
    counts: dict[str, int] = {}
    for item in queue:
        counts[item.project] = counts.get(item.project, 0) + 1
    if not counts:
        return None
    name = max(counts, key=lambda key: counts[key])
    return (name, counts[name]) if counts[name] > 1 else None


def _link(number: str, request_id: int) -> str:
    url = panel_url(f"/requests/{request_id}")
    if not url.startswith("http"):
        return f"<b>{number}</b>"
    return f'<a href="{url}">{number}</a>'


# --- Рассылка --------------------------------------------------------------------------


def send_digests(
    session: Session, kind: IntelligenceKind, *, now: datetime | None = None
) -> str:
    """Рассылает сводку тем, кому пора. Строка — для журнала задач."""
    moment = now or utcnow()
    sent = skipped = failed = 0

    for employee in subscribers(session):
        if not due_now(employee, kind, moment):
            continue
        # Право — в момент отправки. Настройка правом не является.
        if not may_receive(employee):
            skipped += 1
            continue

        key = dedup.digest_key(employee, kind, local_date_of(employee, moment))
        row = dedup.claim(session, employee=employee, kind=kind, key=key)
        if row is None:
            continue

        try:
            message = (
                morning(session, employee, now=moment)
                if kind is IntelligenceKind.MORNING
                else evening(session, employee, now=moment)
            )
        except Exception as exc:  # noqa: BLE001
            # Сбой на одном получателе не отменяет остальных.
            log.exception("Сводка не собралась для %s", employee.id)
            dedup.mark_failed(session, row, f"{type(exc).__name__}: {exc}")
            failed += 1
            continue

        if not message.worth_sending:
            # Разбирать нечего, и человек просил его в этом случае не
            # трогать. Ключ всё равно занимаем: иначе на следующем тике
            # мы снова соберём ту же пустую сводку.
            dedup.mark_skipped(session, row, "изменений за день не было")
            skipped += 1
            continue

        error = delivery.send(employee, message.text, button=message.button)
        if error:
            dedup.mark_failed(session, row, error)
            failed += 1
            continue

        dedup.mark_sent(
            session,
            row,
            result_count=message.result_count,
            ai_used=message.ai_used,
            now=moment,
        )
        sent += 1

    log.info("Сводка %s: отправлено %s, пропущено %s, ошибок %s", kind.value, sent, skipped, failed)
    return f"отправлено {sent}, пропущено {skipped}, ошибок {failed}"


def scan_critical(session: Session, *, now: datetime | None = None) -> str:
    """Ищет критичные проблемы и шлёт сигналы. Строка — для журнала задач.

    Сигнал — не про всякую задержку. Только критичное: превышение
    норматива вдвое и то, что само не рассосётся. Обычная просрочка
    придёт утренней сводкой, и это правильное для неё место.
    """
    moment = now or utcnow()
    sent = repeated = closed = 0

    for employee in subscribers(session):
        if not employee.critical_alerts_enabled or not may_receive(employee):
            continue

        box = scope.for_employee(employee)
        queue = attention.requires_attention(session, now=moment, scope=box)
        critical = [item for item in queue if item.severity == "critical"]

        still_open = {
            dedup.alert_key(employee, item.request_id, item.codes[0] if item.codes else "critical")
            for item in critical
        }
        closed += dedup.resolve_gone(session, employee, still_open, now=moment)

        for item in critical:
            reason = item.codes[0] if item.codes else "critical"
            key = dedup.alert_key(employee, item.request_id, reason)
            row = dedup.claim(
                session,
                employee=employee,
                kind=IntelligenceKind.CRITICAL,
                key=key,
                request_id=item.request_id,
                reason=reason,
            )
            again = False
            if row is None:
                row = dedup.repeatable(session, key, now=moment)
                again = row is not None
            if row is None:
                continue

            head = "Напоминание" if again else "Требует внимания"
            text = (
                f"<b>ORDER • {head}</b>\n\n"
                f"{_link(item.number, item.request_id)} · {item.project}\n"
                f"{item.stage_label}\n"
                f"{'; '.join(item.reasons[:2])}"
            )
            error = delivery.send(
                employee, text, button=("Открыть заявку", panel_url(f"/requests/{item.request_id}"))
            )
            if error:
                dedup.mark_failed(session, row, error)
                continue
            dedup.mark_sent(session, row, result_count=1, now=moment)
            if again:
                repeated += 1
            else:
                sent += 1

    log.info("Сигналы: новых %s, повторов %s, закрыто %s", sent, repeated, closed)
    return f"новых {sent}, повторов {repeated}, закрыто {closed}"


def stats(session: Session, *, days: int = 30) -> dict[str, int]:
    """Метрики рассылки для раздела администратора."""
    from datetime import timedelta

    since = utcnow() - timedelta(days=days)
    rows = session.scalars(
        select(IntelligenceDelivery).where(IntelligenceDelivery.created_at >= since)
    ).all()
    delivered = [r for r in rows if r.delivered_at is not None]
    return {
        "days": days,
        "subscribers": len(subscribers(session)),
        "morning_sent": sum(1 for r in delivered if r.kind is IntelligenceKind.MORNING),
        "evening_sent": sum(1 for r in delivered if r.kind is IntelligenceKind.EVENING),
        "critical_sent": sum(1 for r in delivered if r.kind is IntelligenceKind.CRITICAL),
        "failed": sum(1 for r in rows if not r.ok),
        "ai_digests": sum(1 for r in delivered if r.ai_used),
        "fallback_digests": sum(
            1
            for r in delivered
            if not r.ai_used and r.kind is not IntelligenceKind.CRITICAL
        ),
    }
