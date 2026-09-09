"""Помощник на Claude: один вопрос — один структурированный ответ.

Устроено как почта, Telegram и push в `app/core`: транспорт подменяется в
тестах, а сбой никогда не мешает основному действию — подсказка есть
подсказка, заявку подают и без неё. Здесь только вызов модели; что
спросить и как показать ответ — дело сервисов.
"""

from __future__ import annotations

import logging
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AssistantError(RuntimeError):
    """Модель не ответила. Текст — для лога, не для человека."""


#: Реплика диалога: («user» | «assistant», текст).
Turn = tuple[str, str]


class Transport(Protocol):
    def ask(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        history: list[Turn] | None = None,
        effort: str = "low",
    ) -> T: ...


class ClaudeTransport:
    """Настоящий вызов через официальный SDK. Ответ приходит уже разобранным
    по pydantic-схеме — свободный текст модели парсить не нужно."""

    def ask(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        history: list[Turn] | None = None,
        effort: str = "low",
    ) -> T:
        import anthropic

        settings = get_settings()
        client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.assistant_timeout_seconds,
            max_retries=1,
        )
        try:
            response = client.messages.parse(
                model=settings.assistant_model,
                max_tokens=2048,
                system=system,
                messages=[
                    *({"role": role, "content": text} for role, text in history or []),
                    {"role": "user", "content": prompt},
                ],
                output_format=schema,
                # Проверка написания — задача простая; разбор потребности в
                # диалоге требует больше рассуждения, его зовут с medium.
                output_config={"effort": effort},
            )
        except anthropic.AuthenticationError as exc:
            raise AssistantError("ключ Claude API не принят") from exc
        except anthropic.RateLimitError as exc:
            raise AssistantError("исчерпан лимит запросов к Claude API") from exc
        except anthropic.APIStatusError as exc:
            raise AssistantError(f"Claude API ответил {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise AssistantError("нет связи с Claude API") from exc
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise AssistantError("модель не дала ответ по схеме")
        return response.parsed_output


class NullTransport:
    """Помощник выключен: ключа нет."""

    def ask(
        self,
        *,
        system: str,
        prompt: str,
        schema: type[T],
        history: list[Turn] | None = None,
        effort: str = "low",
    ) -> T:
        raise AssistantError("помощник выключен: не задан ANTHROPIC_API_KEY")


_transport: Transport | None = None


def set_transport(transport: Transport | None) -> None:
    """Подмена вызова. Тесты не должны ходить в сеть."""
    global _transport
    _transport = transport


def _current() -> Transport:
    if _transport is not None:
        return _transport
    return ClaudeTransport() if get_settings().assistant_enabled else NullTransport()


def ask(
    *,
    system: str,
    prompt: str,
    schema: type[T],
    history: list[Turn] | None = None,
    effort: str = "low",
) -> T:
    """Спросить модель и получить ответ по схеме. Бросает AssistantError.

    `history` — предыдущие реплики диалога: помощник задаёт уточняющий
    вопрос и должен помнить, что сотрудник уже ответил.
    """
    return _current().ask(
        system=system, prompt=prompt, schema=schema, history=history, effort=effort
    )
