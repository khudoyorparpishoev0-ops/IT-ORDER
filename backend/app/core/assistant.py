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


class Transport(Protocol):
    def ask(self, *, system: str, prompt: str, schema: type[T]) -> T: ...


class ClaudeTransport:
    """Настоящий вызов через официальный SDK. Ответ приходит уже разобранным
    по pydantic-схеме — свободный текст модели парсить не нужно."""

    def ask(self, *, system: str, prompt: str, schema: type[T]) -> T:
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
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                # Простая задача: короткий ответ по образцу, глубоко думать
                # не над чем.
                output_config={"effort": "low"},
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

    def ask(self, *, system: str, prompt: str, schema: type[T]) -> T:
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


def ask(*, system: str, prompt: str, schema: type[T]) -> T:
    """Спросить модель и получить ответ по схеме. Бросает AssistantError."""
    return _current().ask(system=system, prompt=prompt, schema=schema)
