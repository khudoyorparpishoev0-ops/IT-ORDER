"""Схемы служебного раздела AI. Зеркалятся в frontend/src/api/types.ts."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
    recent: list[AiEntry]


class AiFeedbackIn(BaseModel):
    """Оценка ответа помощника."""

    interaction_id: int
    #: true — «полезно», false — «не подходит».
    useful: bool
    #: Причина отказа из закрытого списка. У «полезно» её нет.
    reason: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=1000)
