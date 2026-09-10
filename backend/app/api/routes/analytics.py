"""Аналитика для руководителя. Только чтение и объяснение.

Раздел закрыт правом `view_reports` целиком: сводка по компании — не
дело рядового сотрудника и не дело отдела закупа. Модель получает
готовые цифры и не может обойти это ограничение вопросом, потому что
данных, которых человеку не положено видеть, в её блоке фактов нет.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession, RequirePermission, bind_audit_actor
from app.core.permissions import Permission
from app.schemas.analytics import (
    AnalyticsAskIn,
    AnalyticsReplyOut,
    AnomalyOut,
    AttentionOut,
    DigestOut,
    DigestOutText,
    ExecutiveOverviewOut,
    IntelligenceOut,
    IssueOut,
    ProblemOut,
    StuckOut,
)
from app.core.time import utcnow
from app.services import analytics, intelligence
from app.services.analytics import anomalies as anomalies_svc
from app.services.analytics import attention as attention_svc
from app.services.analytics import digest as digest_svc
from app.services.analytics import executive as executive_svc
from app.services.analytics import inconsistencies as inc_svc
from app.services.analytics import scope as scope_svc
from app.services.analytics import stale as stale_svc
from app.services.audit import write_audit

router = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
    dependencies=[
        Depends(bind_audit_actor),
        Depends(RequirePermission(Permission.VIEW_REPORTS)),
    ],
)


@router.get("/digest", response_model=DigestOut)
def digest(
    session: DbSession,
    _: CurrentUser,
    ai: bool = Query(
        default=True,
        description="false — только цифры, без обращения к модели и без платы за него",
    ),
):
    """Сводка: счётчики, заявки на внимание, этапы, объекты, тренды.

    Цифры считает сервер, поэтому сводка работает и без AI: без ключа
    просто не будет объясняющего текста. Карточке на дашборде текст не
    нужен — она зовёт этот же эндпоинт с `ai=false`, чтобы каждый заход
    на дашборд не стоил денег.
    """
    if not ai:
        return analytics.digest_facts(session)
    return intelligence.digest(session)


@router.post("/ask", response_model=AnalyticsReplyOut)
def ask(session: DbSession, user: CurrentUser, data: AnalyticsAskIn):
    """Вопрос руководителя обычными словами.

    Пишем в журнал, кто и о чём спрашивал: аналитика показывает данные по
    всей компании, и след обращения должен остаться, как у любого другого
    доступа к чужим заявкам.
    """
    write_audit(
        session,
        entity="analytics",
        entity_id="ask",
        action="ai_question",
        details=data.question.strip()[:500],
    )
    session.commit()
    # Модель называет намерение из разрешённого списка, данные достаёт
    # сервер: произвольный SQL от модели в боевую базу мы не пускаем.
    return intelligence.ask_by_intent(
        session,
        question=data.question,
        history=data.history,
        scope=scope_svc.for_employee(user),
    )


# --------------------------------------------------------------------------
# ORDER Intelligence
# --------------------------------------------------------------------------
def _log(session, user, intent: str, found: int, *, with_ai: bool) -> None:
    """След обращения к аналитике.

    Кто, о чём, сколько нашлось и звали ли модель. Доступ к данным всей
    компании должен оставлять след — как и всякий доступ к чужим заявкам.
    Ни payload, ни ответ модели сюда не пишем: журнал отвечает на вопрос
    «кто смотрел», а не хранит копию отчёта.
    """
    write_audit(
        session,
        entity="analytics",
        entity_id=intent,
        action="ai_question" if with_ai else "analytics_view",
        details=f"{intent}: {found} " + ("с AI" if with_ai else "без AI"),
    )
    session.commit()


def _overview_out(data: executive_svc.Overview) -> ExecutiveOverviewOut:
    return ExecutiveOverviewOut(
        generated_at=data.generated_at,
        active_requests=data.active_requests,
        created_today=data.created_today,
        completed_today=data.completed_today,
        overdue=data.overdue,
        stuck=data.stuck,
        requires_attention=data.requires_attention,
        amount_active=data.amount_active,
        problems=[
            ProblemOut(code=p.code, label=p.label, count=p.count, severity=p.severity)
            for p in data.problems
        ],
    )


@router.get("/executive-overview", response_model=ExecutiveOverviewOut)
def executive_overview(session: DbSession, user: CurrentUser):
    """Состояние компании одним экраном.

    Все числа считает сервер. Модель их не пересчитывает и не угадывает:
    по этим цифрам распоряжаются деньгами, а правдоподобная выдумка тут
    дороже отсутствия цифры.
    """
    box = scope_svc.for_employee(user)
    data = executive_svc.overview(session, scope=box)
    _log(session, user, "overview", data.requires_attention, with_ai=False)
    return _overview_out(data)


@router.get("/intelligence", response_model=IntelligenceOut)
def intelligence_section(
    session: DbSession,
    user: CurrentUser,
    ai: bool = Query(
        default=True,
        description="false — только цифры, без обращения к модели и платы за него",
    ),
):
    """Раздел ORDER Intelligence целиком: сводка, очередь внимания,
    застой, нестыковки и отклонения от обычного уровня."""
    box = scope_svc.for_employee(user)
    now = utcnow()

    # Все разделы берут заявки из одной точки в границах видимости:
    # забыть ограничение в одном из них так невозможно.
    rows = stale_svc.in_work(session, scope=box)
    data = executive_svc.overview(session, now=now, scope=box)
    queue = attention_svc.requires_attention(session, now=now, scope=box)
    stuck = stale_svc.stuck_requests(session, now=now, rows=rows)
    issues = inc_svc.find_all(session, now=now, rows=rows)
    deviations = anomalies_svc.find(session, now=now)

    text = (
        intelligence.explain_overview(session, data, queue, deviations)
        if ai
        else intelligence.no_ai()
    )
    _log(session, user, "intelligence", len(queue), with_ai=ai)

    return IntelligenceOut(
        overview=_overview_out(data),
        attention=[AttentionOut(**vars(i)) for i in queue],
        stuck=[StuckOut(**vars(s)) for s in stuck[:20]],
        issues=[IssueOut(**vars(i)) for i in issues[:20]],
        anomalies=[AnomalyOut(**vars(a)) for a in deviations],
        ai=text,
        blind_spots=analytics.BLIND_SPOTS,
    )


@router.get("/digest/{kind}", response_model=DigestOutText)
def digest_text(session: DbSession, user: CurrentUser, kind: str):
    """Утренняя или вечерняя сводка — та же, что уходит письмом и в бот."""
    box = scope_svc.for_employee(user)
    data = (
        digest_svc.evening(session, scope=box)
        if kind == "evening"
        else digest_svc.morning(session, scope=box)
    )
    _log(session, user, f"digest_{data.kind}", len(data.problems), with_ai=False)
    return DigestOutText(
        kind=data.kind,
        title=data.title,
        lines=data.lines,
        problems=data.problems,
        text=digest_svc.as_text(data),
    )
