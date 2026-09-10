"""Схемы служебного раздела AI. Зеркалятся в frontend/src/api/types.ts."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.analytics import DeliveryStatsOut


class AiReasonCount(BaseModel):
    """Причина отрицательной оценки и сколько раз её выбрали."""

    reason: str
    label: str
    count: int


class AiUsage(BaseModel):
    """Сколько помощником пользовались и с каким успехом.

    Все числа считает база (`services/ai_log.py`, `services/ai_feedback.py`).
    Модель их не видит и не считает: по таким цифрам судят о расходах, а
    правдоподобная выдумка здесь дороже отсутствия цифры.
    """

    days: int
    total: int
    #: Из них модель не ответила: нет ключа, таймаут, отказ Anthropic.
    failed: int
    #: Доля отказов в процентах.
    error_pct: int | None
    #: Из них человек нажал «Применить».
    applied: int
    #: Доля применённых от отвеченных, в процентах.
    apply_rate_pct: int | None
    #: Среднее время ответа, секунд. None — ответов не было.
    avg_seconds: float | None
    #: Обращения по видам помощника: material / request / analytics.
    by_kind: dict[str, int]
    #: Обращений за 7 дней — для сравнения с 30-дневным окном.
    total_week: int
    #: Токены за период. None — Anthropic статистику не вернул.
    input_tokens: int | None
    output_tokens: int | None
    #: Оценки людей.
    useful: int
    useless: int
    useless_pct: int | None
    top_reasons: list[AiReasonCount] = []


class AiEntry(BaseModel):
    """Строка журнала обращений."""

    id: int
    kind: str
    source: str
    username: str | None
    question: str | None
    answer: str | None
    ok: bool
    error: str | None
    applied: bool | None
    duration_ms: int | None
    created_at: str


class AiSettingsOut(BaseModel):
    """Состояние помощника для администратора.

    Ключ Anthropic здесь только замаскированный и только для того, чтобы
    администратор убедился, что в `.env` лежит тот ключ, который он туда
    положил. Целиком ключ не покидает сервер никогда.
    """

    enabled: bool
    model: str
    key_mask: str | None
    timeout_seconds: int
    #: Правила помощника заменены файлом (ASSISTANT_PROMPT_FILE).
    prompt_overridden: bool
    #: Правила аналитика заменены файлом (ANALYTICS_PROMPT_FILE).
    analytics_prompt_overridden: bool
    usage: AiUsage
    #: Автоматические сводки ORDER Intelligence за последний месяц.
    deliveries: DeliveryStatsOut
    recent: list[AiEntry]


class AiFeedbackIn(BaseModel):
    """Оценка ответа помощника."""

    interaction_id: int
    #: true — «полезно», false — «не подходит».
    useful: bool
    #: Причина отказа из закрытого списка. У «полезно» её нет.
    reason: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=1000)


class AiPeriodOut(BaseModel):
    """Показатели за отрезок времени."""

    label: str
    days: int
    requests: int
    #: Доллары. Строкой, как и суммы в сомони: перевод в число теряет
    #: доли цента, а из них и складывается месячный расход.
    cost_usd: Decimal
    #: Сумма посчитана по нынешней цене, а не по снимку (старые записи).
    estimated: bool
    input_tokens: int
    output_tokens: int
    avg_seconds: float | None
    error_pct: int | None
    avoided: int
    avoided_pct: int | None


class AiModelOut(BaseModel):
    model: str | None
    requests: int
    cost_usd: Decimal
    avg_seconds: float | None
    #: Цена модели известна. False — сумма занижена, и это видно.
    price_known: bool

    # `model` — служебное имя в pydantic; поле ниже разрешает его как
    # обычное. Без этого pydantic ругается на «model_» на старте.
    model_config = {"protected_namespaces": ()}


class AiUsageTypeOut(BaseModel):
    key: str
    label: str
    requests: int
    cost_usd: Decimal
    avg_tokens: int | None
    apply_rate_pct: int | None
    #: Скольким ответам предлагали кнопку «Применить».
    offered: int


class AiEmployeeCostOut(BaseModel):
    """Расход по сотрудникам. Метрика использования, не оценка людей."""

    employee: str
    requests: int
    tokens: int
    cost_usd: Decimal


class AiBudgetOut(BaseModel):
    """Бюджет месяца. Помощник по нему не выключается."""

    limit_usd: Decimal | None
    spent_usd: Decimal
    used_pct: int | None
    warning_percent: int
    warning: bool


class AiFeedbackSummaryOut(BaseModel):
    useful: int
    useless: int
    #: Доля отвеченных обращений, которые вообще оценили.
    feedback_rate_pct: int | None
    useless_pct: int | None
    top_reasons: list[AiReasonCount] = []


class AiUsageOut(BaseModel):
    """Раздел «Расход AI» целиком."""

    periods: list[AiPeriodOut] = []
    models: list[AiModelOut] = []
    usage_types: list[AiUsageTypeOut] = []
    employees: list[AiEmployeeCostOut] = []
    feedback: AiFeedbackSummaryOut
    budget: AiBudgetOut
    #: Доля применённых среди ответов, где кнопка была.
    apply_rate_pct: int | None
    applied: int
    offered: int
    #: На какую дату сверялся прайс Anthropic.
    prices_checked: str
