"""Схемы служебного раздела AI. Зеркалятся в frontend/src/api/types.ts."""

from __future__ import annotations

from pydantic import BaseModel


class AiUsage(BaseModel):
    """Сколько помощником пользовались и с каким успехом."""

    days: int
    total: int
    #: Из них модель не ответила: нет ключа, таймаут, отказ Anthropic.
    failed: int
    #: Из них человек нажал «Применить».
    applied: int
    #: Среднее время ответа, секунд. None — ответов не было.
    avg_seconds: float | None
    #: Обращения по видам помощника: material / request / analytics.
    by_kind: dict[str, int]


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
