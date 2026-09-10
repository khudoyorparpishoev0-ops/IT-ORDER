"""Схемы аналитики для руководителя. Зеркалятся в frontend/src/api/types.ts.

Все числа считает сервер (`app/services/analytics.py`). Модель получает
готовые факты и только объясняет их словами — считать ей нельзя.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

#: Насколько заявка требует внимания. Цвет в панели даёт `data/status.ts`.
Level = Literal["critical", "attention", "normal"]

#: Насколько всё плохо в разделе ORDER Intelligence. Отдельно от `Level`:
#: там речь о заявке («требует внимания»), здесь — о находке («критично,
#: тревожно, к сведению»), и смешивать их значит однажды покрасить
#: справочное замечание в красный.
Severity = Literal["critical", "warning", "info"]


class AttentionItem(BaseModel):
    """Заявка, на которую стоит посмотреть, и почему именно."""

    id: int
    number: str
    title: str
    project: str
    employee: str
    #: Кто держит заявку сейчас: «Отдел закупа», «Руководитель».
    holder: str
    stage: str
    stage_label: str
    #: Сколько часов заявка стоит на текущем шаге.
    hours: int
    #: Норматив для шага, часов. None — норматива нет (черновик).
    norm_hours: int | None
    level: Level
    #: Человеческие причины: «стоит 31 час при норме 8».
    reasons: list[str]
    amount: Decimal
    priced: bool


class RequestBrief(BaseModel):
    """Строка заявки в работе. Нужна, чтобы аналитик мог отвечать на
    вопросы вроде «какие заявки объекта Регар» и «что дороже 1000»."""

    id: int
    number: str
    title: str
    project: str
    employee: str
    holder: str
    hours: int
    amount: Decimal
    priced: bool


class StageStat(BaseModel):
    """Этап пути заявки: сколько стоит и укладывается ли в норматив."""

    key: str
    label: str
    count: int
    #: Среднее время ожидания на этапе прямо сейчас, часов.
    avg_hours: float | None
    #: Сколько заявок этапа вышло за норматив.
    over_norm: int
    norm_hours: int | None
    #: Среднее фактическое время прохождения этапа за 30 дней, часов.
    done_avg_hours: float | None
    #: То же за предыдущие 30 дней — видно, стало быстрее или медленнее.
    done_prev_avg_hours: float | None


class ProjectStat(BaseModel):
    """Объект: сколько заявок и денег за месяц."""

    id: int
    name: str
    active_count: int
    month_count: int
    month_amount: Decimal
    #: Заявки объекта, вышедшие за норматив.
    over_norm: int
    #: Что чаще всего просят на объекте за месяц.
    top_materials: list[str]


class PersonStat(BaseModel):
    """Сотрудник: только факты, без оценок работы."""

    id: int
    name: str
    role: str
    #: Сколько заявок ждёт решения именно этого человека сейчас.
    holding: int
    #: Из них вышли за норматив.
    over_norm: int
    #: Сколько заявок подал за месяц (для автора).
    created_month: int


class DuplicatePair(BaseModel):
    """Две похожие заявки одного объекта. Решение — за человеком."""

    first_id: int
    first_number: str
    second_id: int
    second_number: str
    project: str
    #: Совпавшие позиции.
    materials: list[str]
    hours_apart: int


class Trend(BaseModel):
    """Показатель этой недели против прошлой."""

    label: str
    current: float
    previous: float
    #: Изменение в процентах; None — сравнивать не с чем.
    change_pct: float | None
    #: Единица для панели: «заявок», «сомони».
    unit: str


class Totals(BaseModel):
    """Счётчики на сегодня и за период."""

    active: int
    drafts: int
    created_today: int
    created_week: int
    created_month: int
    #: Оплачено и закрыто складом за сегодня.
    done_today: int
    done_month: int
    rejected_month: int
    critical: int
    attention: int
    over_norm: int
    to_pay_amount: Decimal
    to_pay_count: int
    paid_month_amount: Decimal
    paid_month_count: int
    budget_amount: Decimal | None
    budget_used_pct: int | None
    #: Среднее время от подачи до выплаты за месяц, суток.
    avg_cycle_days: float | None


class AiText(BaseModel):
    """Слова модели поверх готовых чисел."""

    enabled: bool
    available: bool
    #: Одна фраза-вывод: «На вас три решения, две заявки задержались».
    headline: str | None = None
    #: Что происходит и где проблема, по пунктам.
    summary: list[str] = []
    #: Что имеет смысл сделать. Рекомендации, не действия.
    recommendations: list[str] = []


class DigestOut(BaseModel):
    """Сводка для руководителя: числа сервера плюс объяснение модели."""

    generated_at: str
    ai: AiText
    totals: Totals
    attention: list[AttentionItem]
    #: Заявки в работе: по ним аналитик отвечает на частные вопросы.
    in_work: list[RequestBrief]
    stages: list[StageStat]
    projects: list[ProjectStat]
    people: list[PersonStat]
    duplicates: list[DuplicatePair]
    trends: list[Trend]
    #: Чего система не знает: нет накладных, нет отделов. Честно говорим.
    blind_spots: list[str] = []


class AnalyticsTurn(BaseModel):
    """Реплика диалога. Историю хранит панель, на сервере состояния нет."""

    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)


class AnalyticsAskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[AnalyticsTurn] = Field(default_factory=list, max_length=16)


class AnalyticsRequestRef(BaseModel):
    """Заявка, на которую ссылается ответ: в панели это ссылка."""

    id: int
    number: str
    why: str


class AnalyticsReplyOut(BaseModel):
    """Ответ аналитика на вопрос руководителя."""

    enabled: bool
    available: bool
    answer: str = ""
    bullets: list[str] = []
    requests: list[AnalyticsRequestRef] = []
    recommendations: list[str] = []


# --- ORDER Intelligence: сводка руководителя ----------------------------------


class ProblemOut(BaseModel):
    """Строка блока «требует внимания» на дашборде директора."""

    code: str
    label: str
    count: int
    severity: Severity


class ExecutiveOverviewOut(BaseModel):
    """Состояние компании одним экраном. Все числа считает сервер."""

    generated_at: str
    active_requests: int
    created_today: int
    completed_today: int
    #: Вышли за норматив своего этапа.
    overdue: int
    #: Стоят без движения, но норматив ещё не нарушен.
    stuck: int
    #: Сколько заявок требуют внимания — без двойного счёта.
    requires_attention: int
    amount_active: Decimal
    problems: list[ProblemOut] = []


class StuckOut(BaseModel):
    """Заявка без движения: где стоит, сколько и у кого."""

    request_id: int
    number: str
    title: str
    project: str
    employee: str
    status: str
    stage_label: str
    hours_in_status: int
    norm_hours: int | None
    assignee: str
    severity: Severity
    overdue: bool
    reason: str


class IssueOut(BaseModel):
    """Нестыковка в заявке. Факт, а не обвинение."""

    request_id: int
    number: str
    title: str
    project: str
    employee: str
    severity: Severity
    code: str
    detail: str


class AnomalyOut(BaseModel):
    """Показатель, отличающийся от обычного уровня."""

    code: str
    subject: str
    current: float
    previous: float
    change_pct: int
    unit: str
    detail: str
    severity: Severity


class AttentionOut(BaseModel):
    """Заявка в очереди внимания со всеми причинами разом."""

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
    severity: Severity
    reasons: list[str] = []
    codes: list[str] = []


class IntelligenceOut(BaseModel):
    """Раздел ORDER Intelligence целиком."""

    overview: ExecutiveOverviewOut
    attention: list[AttentionOut] = []
    stuck: list[StuckOut] = []
    issues: list[IssueOut] = []
    anomalies: list[AnomalyOut] = []
    #: Слова модели поверх готовых чисел. Без ключа — enabled=false.
    ai: AiText
    blind_spots: list[str] = []


class DigestOutText(BaseModel):
    """Утренняя или вечерняя сводка одним сообщением."""

    kind: str
    title: str
    lines: list[str] = []
    problems: list[str] = []
    text: str
