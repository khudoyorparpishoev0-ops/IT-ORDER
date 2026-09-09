"""Проверка помощника одной командой.

    docker compose exec api python -m app.assistant_check

Делает один настоящий запрос к Claude и печатает, что ответили. Разбор
«почему помощник молчит» через панель требует до неё добраться, а в логе
причина видна только тому, кто знает, что грепать. Ключ не печатается.
"""

from __future__ import annotations

import sys
import time

from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.assistant import AssistantError, ask

#: Что делать с самыми частыми отказами. Ключ — что искать в тексте.
HINTS: tuple[tuple[str, str], ...] = (
    (
        "credit",
        "На счёте Claude нет средств. Пополните баланс:\n"
        "  console.anthropic.com → Billing → Add credits.",
    ),
    (
        "не принят",
        "Ключ не подошёл. Возьмите новый на console.anthropic.com → API Keys\n"
        "  и впишите в .env строкой ANTHROPIC_API_KEY=, затем docker compose up -d api.",
    ),
    (
        "не ответил за",
        "Модель не уложилась в отведённое время. Поднимите срок в .env:\n"
        "  ASSISTANT_TIMEOUT_SECONDS=120, затем docker compose up -d api.",
    ),
    (
        "model",
        "Модель не найдена. Проверьте ASSISTANT_MODEL в .env "
        "(по умолчанию claude-opus-5).",
    ),
)


class _Answer(BaseModel):
    ok: bool = Field(description="Всегда true")
    word: str = Field(description="Одно слово: работает")


def main() -> int:
    settings = get_settings()
    print(f"Модель:  {settings.assistant_model}")
    print(f"Таймаут: {settings.assistant_timeout_seconds} с")
    if not settings.assistant_enabled:
        print(
            "\nПомощник выключен: не задан ANTHROPIC_API_KEY.\n"
            "Впишите ключ в .env и примените: docker compose up -d api.\n"
            "Если ключ в .env уже есть — проверьте, что он передан контейнеру\n"
            "строкой ANTHROPIC_API_KEY в docker-compose.yml."
        )
        return 1

    print("\nСпрашиваю модель…")
    started = time.monotonic()
    try:
        answer = ask(
            system="Ты отвечаешь одним словом.",
            prompt="Ответь: ok=true, word=работает",
            schema=_Answer,
        )
    except AssistantError as exc:
        text = str(exc)
        print(f"\nНе получилось: {text}")
        for needle, hint in HINTS:
            if needle in text.lower() or needle in text:
                print(f"\n{hint}")
                break
        return 1
    print(f"Ответ получен за {time.monotonic() - started:.1f} с: {answer.word}")
    print("\nПомощник работает.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
