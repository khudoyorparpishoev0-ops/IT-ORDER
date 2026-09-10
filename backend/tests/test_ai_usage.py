"""Расход на AI: сколько стоит, кто применил, что закрыли без модели.

По этим цифрам решают, продолжать ли платить за помощника. Поэтому
проверяется в первую очередь то, что может соврать про деньги: снимок
цены, неизвестная модель, пустые токены и знаменатель доли применённых.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest

from app.config import get_settings
from app.core.assistant import Usage
from app.core.audit_context import Actor, set_actor
from app.core.time import to_local, utcnow
from app.db.models import AiInteraction, AiKind, AiResolvedBy, AiSource
from app.services import ai_log, ai_pricing, ai_usage

MODEL = "claude-opus-5"


@pytest.fixture(autouse=True)
def _fresh_prices():
    """Цены читаются заново: тест мог подменить их файлом."""
    ai_pricing.reload()
    yield
    ai_pricing.reload()


def ask(
    session,
    *,
    kind: AiKind = AiKind.MATERIAL,
    source: AiSource = AiSource.WEB,
    model: str | None = MODEL,
    tokens: tuple[int | None, int | None] = (1000, 500),
    ok: bool = True,
    resolved_by: AiResolvedBy | None = None,
    offers_apply: bool = True,
    ms: int | None = 1200,
    who: str = "Артём Ковалёв",
) -> AiInteraction:
    """Одно обращение в журнале. Возвращает саму запись."""
    set_actor(Actor(id=None, name=who))
    usage = Usage(model=model, input_tokens=tokens[0], output_tokens=tokens[1]) if model else None
    entry_id = ai_log.record(
        session,
        kind=kind,
        source=source,
        question="Цемент М500",
        answer="Цемент М500",
        ok=ok,
        duration_ms=ms,
        usage=usage,
        resolved_by=resolved_by,
        offers_apply=offers_apply,
    )
    set_actor(None)
    return session.get(AiInteraction, entry_id)


def age(session, entry: AiInteraction, *, days: int) -> None:
    entry.created_at = utcnow() - timedelta(days=days)
    session.commit()


# --- Стоимость ---------------------------------------------------------------------


def test_cost_is_counted_per_million_tokens() -> None:
    """Opus 5: пять долларов за миллион входных, двадцать пять за выход."""
    cost = ai_pricing.cost(MODEL, 1_000_000, 1_000_000)
    assert cost == Decimal("30.000000")

    small = ai_pricing.cost(MODEL, 1000, 500)
    assert small == Decimal("0.017500")


def test_cost_is_written_as_a_snapshot(session) -> None:
    entry = ask(session)
    assert entry.cost_usd == Decimal("0.017500")
    assert entry.resolved_by is AiResolvedBy.MODEL


def test_price_change_does_not_rewrite_history(session, tmp_path, monkeypatch) -> None:
    """Подорожала модель — прошлый месяц остаётся прежним.

    Снимок и есть та цена, по которой заплатили. Пересчёт задним числом
    означал бы, что расход за март меняется в апреле, и сверить его со
    счётом Anthropic станет нечем.
    """
    entry = ask(session)
    was = entry.cost_usd

    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps({MODEL: {"input": "50", "output": "250"}}))
    monkeypatch.setattr(get_settings(), "ai_prices_file", str(prices))
    ai_pricing.reload()

    assert ai_pricing.cost(MODEL, 1000, 500) == Decimal("0.175000")
    data = ai_usage.collect(session)
    assert data.periods[2].cost_usd == was
    assert data.periods[2].estimated is False


def test_unknown_model_costs_nothing_but_is_visible(session) -> None:
    """Неизвестная модель — не ноль, а «цену не знаем»."""
    ask(session, model="claude-из-будущего-9")

    assert ai_pricing.cost("claude-из-будущего-9", 1000, 500) is None
    row = next(m for m in ai_usage.collect(session).models if m.model == "claude-из-будущего-9")
    assert row.price_known is False
    assert row.requests == 1


def test_missing_tokens_do_not_break_the_count(session) -> None:
    """SDK не отдал статистику — считаем то, что есть, и не падаем."""
    ask(session, tokens=(None, None))

    data = ai_usage.collect(session)
    assert data.periods[2].requests == 1
    assert data.periods[2].cost_usd == Decimal("0")
    assert data.periods[2].input_tokens == 0


def test_broken_price_file_falls_back(tmp_path, monkeypatch) -> None:
    """Битый файл цен не роняет ни расход, ни помощника."""
    bad = tmp_path / "prices.json"
    bad.write_text("{это не json")
    monkeypatch.setattr(get_settings(), "ai_prices_file", str(bad))
    ai_pricing.reload()

    assert ai_pricing.cost(MODEL, 1_000_000, 0) == Decimal("5.000000")


# --- Без модели --------------------------------------------------------------------


def test_alias_and_cache_count_as_answered_without_the_model(session) -> None:
    ask(session, model=None, resolved_by=AiResolvedBy.ALIAS, ms=None)
    ask(session, model=None, resolved_by=AiResolvedBy.CACHE, ms=None)
    ask(session)

    month = ai_usage.collect(session).periods[2]
    assert month.avoided == 2
    assert month.avoided_pct == 67


def test_answers_without_the_model_are_free(session) -> None:
    ask(session, model=None, resolved_by=AiResolvedBy.ALIAS, ms=None)

    data = ai_usage.collect(session)
    assert data.periods[2].cost_usd == Decimal("0")
    # В разбивку по моделям такие обращения не попадают вовсе: модели
    # там не было.
    assert data.models == []


# --- Доля применённых --------------------------------------------------------------


def test_apply_rate_counts_only_answers_that_offered_the_button(session) -> None:
    """Вопрос аналитику знаменатель не портит.

    До фазы 6 доля применённых делилась на все ответы подряд, включая
    те, где кнопки «Применить» нет вовсе, и была заниженной.
    """
    applied = ask(session)
    ask(session)
    ask(session, kind=AiKind.ANALYTICS, offers_apply=False)
    ask(session, kind=AiKind.ANALYTICS, offers_apply=False)

    applied.applied = True
    session.commit()

    data = ai_usage.collect(session)
    assert data.offered == 2
    assert data.applied == 1
    assert data.apply_rate_pct == 50


def test_apply_rate_is_none_without_offers(session) -> None:
    ask(session, kind=AiKind.ANALYTICS, offers_apply=False)
    assert ai_usage.collect(session).apply_rate_pct is None


# --- Разрезы -----------------------------------------------------------------------


def test_usage_types_separate_the_scheduler_from_people(session) -> None:
    """Ночная сводка и руководитель у экрана — разный расход."""
    ask(session, kind=AiKind.ANALYTICS, source=AiSource.SCHEDULER, offers_apply=False)
    ask(session, kind=AiKind.ANALYTICS, source=AiSource.WEB, offers_apply=False)

    keys = {row.key: row for row in ai_usage.collect(session).usage_types}
    assert keys["ANALYTICS:SCHEDULER"].label == "Автоматические сводки"
    assert keys["ANALYTICS:WEB"].requests == 1


def test_employee_costs_are_listed(session) -> None:
    ask(session, who="Артём Ковалёв")
    ask(session, who="Артём Ковалёв")
    ask(session, who="Иван Петров")

    rows = {e.employee: e for e in ai_usage.collect(session).employees}
    assert rows["Артём Ковалёв"].requests == 2
    assert rows["Артём Ковалёв"].cost_usd == Decimal("0.035000")
    assert rows["Иван Петров"].tokens == 1500


def test_periods_split_by_age(session) -> None:
    fresh = ask(session)
    week = ask(session)
    month = ask(session)
    age(session, week, days=3)
    age(session, month, days=20)

    today, seven, thirty = ai_usage.collect(session).periods
    assert (today.requests, seven.requests, thirty.requests) == (1, 2, 3)
    assert fresh.created_at is not None


def test_error_rate_is_counted(session) -> None:
    ask(session)
    ask(session, ok=False, model=None)

    assert ai_usage.collect(session).periods[2].error_pct == 50


# --- Оценки ------------------------------------------------------------------------


def test_feedback_rate_and_reasons(session, client, login, employee) -> None:
    entry = ask(session, who=employee.full_name)
    entry.employee_id = employee.id
    session.commit()

    login(employee)
    assert (
        client.post(
            "/api/ai/feedback",
            json={"interaction_id": entry.id, "useful": False, "reason": "wrong_material"},
        ).status_code
        == 204
    )

    data = ai_usage.collect(session).feedback
    assert data["useless"] == 1
    assert data["feedback_rate_pct"] == 100
    assert data["top_reasons"][0]["label"] == "Неправильный материал"


# --- Бюджет ------------------------------------------------------------------------


def test_budget_warns_at_the_threshold(session, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", Decimal("0.02"))
    monkeypatch.setattr(settings, "ai_budget_warning_percent", 80)

    ask(session)  # 0,0175 — это 88% от двух центов

    budget = ai_usage.collect(session).budget
    assert budget.used_pct == 88
    assert budget.warning is True


def test_budget_does_not_disable_the_assistant(session, monkeypatch) -> None:
    """Порог — повод человеку решить, а не системе выключить помощника.

    Автоотключения нет намеренно: помощник, замолчавший посреди рабочего
    дня, останавливает работу людей, а перерасход — это разговор с
    владельцем, а не аварийная остановка.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_monthly_budget_usd", Decimal("0.001"))
    ask(session)

    data = ai_usage.collect(session)
    assert data.budget.used_pct > 100
    assert settings.assistant_enabled == bool(settings.anthropic_api_key)


def test_budget_is_silent_when_not_set(session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_monthly_budget_usd", Decimal("0"))
    ask(session)

    budget = ai_usage.collect(session).budget
    assert budget.limit_usd is None
    assert budget.used_pct is None
    assert budget.warning is False


def test_budget_counts_the_calendar_month(session) -> None:
    """Счёт Anthropic приходит за календарный месяц, не за 30 дней."""
    old = ask(session)
    local = to_local(utcnow())
    # Первое число прошлого месяца заведомо вне текущего календарного.
    old.created_at = (local.replace(day=1) - timedelta(days=2)).astimezone(
        old.created_at.tzinfo
    )
    session.commit()
    ask(session)

    assert ai_usage.collect(session).budget.spent_usd == Decimal("0.017500")


# --- Права и устойчивость ----------------------------------------------------------


def test_dashboard_is_admin_only(client, session, login, admin, manager, employee) -> None:
    login(employee)
    assert client.get("/api/ai/usage").status_code == 403

    login(manager)
    assert client.get("/api/ai/usage").status_code == 403

    login(admin)
    assert client.get("/api/ai/usage").status_code == 200


def test_dashboard_works_without_anthropic(client, session, login, admin) -> None:
    """Раздел читает журнал, а не спрашивает модель.

    Транспорт помощника в тестах по умолчанию выключен — значит этот
    тест и проверяет, что недоступность Anthropic на раздел не влияет.
    """
    ask(session)

    login(admin)
    body = client.get("/api/ai/usage").json()

    assert body["periods"][2]["requests"] == 1
    assert body["periods"][2]["cost_usd"] == "0.017500"
    assert body["prices_checked"] == ai_pricing.PRICES_CHECKED
