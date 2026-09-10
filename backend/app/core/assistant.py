"""Помощник на Claude: один вопрос — один структурированный ответ.

Устроено как почта, Telegram и push в `app/core`: транспорт подменяется в
тестах, а сбой никогда не мешает основному действию — подсказка есть
подсказка, заявку подают и без неё. Здесь только вызов модели; что
спросить и как показать ответ — дело сервисов.
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AssistantError(RuntimeError):
    """Модель не ответила. Текст — для лога и диагностики, не для человека."""


def _reason(exc) -> str:
    """Человеческая причина отказа из ответа Anthropic."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
    return str(getattr(exc, "message", "") or exc)


#: Реплика диалога: («user» | «assistant», текст).
Turn = tuple[str, str]


@dataclass(frozen=True)
class Usage:
    """Чем обошёлся ответ: модель и токены.

    Нужна для расчёта стоимости ORDER AI: без токенов она известна
    только из счёта Anthropic, то есть задним числом и целиком, без
    разбивки по помощникам. Поля необязательные: SDK может не вернуть
    статистику, и метрики обязаны это пережить.
    """

    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


#: Статистика последнего ответа. Отдаётся отдельно, а не в возвращаемом
#: значении: у `ask` контракт «схема на входе — объект схемы на выходе»,
#: и ломать его ради служебной метрики во всех вызывающих незачем.
_last_usage: ContextVar[Usage | None] = ContextVar("assistant_usage", default=None)


def last_usage() -> Usage | None:
    """Чем обошёлся последний ответ в этом запросе."""
    return _last_usage.get()


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
        started = time.monotonic()
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
            raise AssistantError(
                "ключ Claude API не принят: проверьте ANTHROPIC_API_KEY"
            ) from exc
        except anthropic.RateLimitError as exc:
            raise AssistantError("исчерпан лимит запросов к Claude API") from exc
        except anthropic.APIStatusError as exc:
            # Текст ошибки от Anthropic говорит по делу: кончились кредиты,
            # неизвестная модель, слишком длинный запрос. Прячем его — и
            # разбор превращается в гадание.
            raise AssistantError(
                f"Claude API ответил {exc.status_code}: {_reason(exc)}"
            ) from exc
        except anthropic.APITimeoutError as exc:
            # Наследник APIConnectionError, поэтому ловится раньше него.
            raise AssistantError(
                f"Claude API не ответил за {settings.assistant_timeout_seconds} с "
                f"(ASSISTANT_TIMEOUT_SECONDS)"
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise AssistantError(f"нет связи с Claude API: {exc}") from exc
        if response.stop_reason == "refusal":
            raise AssistantError("модель отклонила запрос")
        if response.parsed_output is None:
            raise AssistantError("модель не дала ответ по схеме")
        usage = getattr(response, "usage", None)
        _last_usage.set(
            Usage(
                # Что ответило на самом деле. В настройке может стоять
                # алиас, а Anthropic разворачивает его в конкретный
                # снимок — по счёту платят за снимок, и в журнале должен
                # стоять он же.
                model=getattr(response, "model", None) or settings.assistant_model,
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
            )
        )
        log.info(
            "Помощник ответил за %.1f с (модель %s, effort %s, токены %s/%s)",
            time.monotonic() - started,
            settings.assistant_model,
            effort,
            getattr(usage, "input_tokens", "—"),
            getattr(usage, "output_tokens", "—"),
        )
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
    # Сбрасываем перед вызовом: иначе при отказе модели в журнал попала
    # бы статистика предыдущего, удачного ответа.
    _last_usage.set(None)
    return _current().ask(
        system=system, prompt=prompt, schema=schema, history=history, effort=effort
    )
