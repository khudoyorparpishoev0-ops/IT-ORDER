"""Сколько стоит обращение к модели.

Одна таблица цен на весь проект. В интерфейс цены не попадают вовсе:
панель показывает уже посчитанную сумму, как и с сомони — считает сервер.

## Почему цены можно подменить файлом

Anthropic меняет прайс чаще, чем мы выкатываем релизы, а расход считается
каждый день. `AI_PRICES_FILE` позволяет поправить цифру на сервере и
перезапустить контейнер, не пересобирая образ, — тот же приём, что у
правил помощника (`ASSISTANT_PROMPT_FILE`).

## Почему неизвестная модель стоит `None`, а не ноль

Ноль означает «бесплатно», и в сводке расход выглядел бы меньше, чем он
есть. `None` означает «не знаем» — и это видно отдельной строкой
«цена неизвестна: N обращений». Врать в меньшую сторону про деньги
нельзя: по этим цифрам решают, продолжать ли платить за помощника.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)

#: Дата, на которую сверялся прайс. Цены меняются — если расход перестал
#: сходиться со счётом Anthropic, начинать разбор надо отсюда.
PRICES_CHECKED = "2026-09-10"

#: Токенов в единице цены. Anthropic считает за миллион.
PER = Decimal("1000000")


@dataclass(frozen=True)
class Price:
    """Цена модели в долларах за миллион токенов."""

    input: Decimal
    output: Decimal


#: Прайс Anthropic (первая сторона, без Bedrock и Vertex — у них свои
#: цены, а ORDER ходит напрямую).
PRICES: dict[str, Price] = {
    "claude-opus-5": Price(Decimal("5"), Decimal("25")),
    "claude-opus-4-8": Price(Decimal("5"), Decimal("25")),
    "claude-opus-4-7": Price(Decimal("5"), Decimal("25")),
    "claude-opus-4-6": Price(Decimal("5"), Decimal("25")),
    "claude-sonnet-5": Price(Decimal("2"), Decimal("10")),
    "claude-sonnet-4-6": Price(Decimal("3"), Decimal("15")),
    "claude-haiku-4-5": Price(Decimal("1"), Decimal("5")),
    "claude-fable-5": Price(Decimal("10"), Decimal("50")),
    "claude-fable-5-1": Price(Decimal("10"), Decimal("50")),
}


@lru_cache(maxsize=1)
def table() -> dict[str, Price]:
    """Цены с учётом подмены файлом. Кэш сбрасывает `reload()`.

    Формат файла — тот же, что таблица выше:

        {"claude-opus-5": {"input": "5", "output": "25"}}

    Битый файл не роняет приложение и не обнуляет расход: пишем в лог и
    работаем по встроенной таблице. Помощник и панель важнее, чем
    точность цены за вчера.
    """
    prices = dict(PRICES)
    path = (get_settings().ai_prices_file or "").strip()
    if not path:
        return prices

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        for model, value in raw.items():
            prices[str(model)] = Price(
                Decimal(str(value["input"])), Decimal(str(value["output"]))
            )
    except Exception:  # noqa: BLE001 — цены не важнее работы приложения
        log.warning("Не удалось прочитать цены из %s", path, exc_info=True)
        return dict(PRICES)

    log.info("Цены моделей взяты из %s: %s позиций", path, len(raw))
    return prices


def reload() -> None:
    """Забыть прочитанный файл. Нужно тестам и смене настроек."""
    table.cache_clear()


def price_of(model: str | None) -> Price | None:
    """Цена модели. None — модель незнакомая или её не назвали."""
    if not model:
        return None
    return table().get(model.strip())


def cost(
    model: str | None, input_tokens: int | None, output_tokens: int | None
) -> Decimal | None:
    """Во что обошлось обращение, в долларах. None — посчитать нечем.

    Нечем — это либо незнакомая модель, либо не пришедшая статистика
    токенов (SDK может её не отдать). Оба случая честнее показать
    пропуском, чем нулём.
    """
    price = price_of(model)
    if price is None:
        return None
    if input_tokens is None and output_tokens is None:
        return None

    total = (Decimal(input_tokens or 0) / PER) * price.input + (
        Decimal(output_tokens or 0) / PER
    ) * price.output
    # Шесть знаков: одно обращение стоит доли цента, и округление до
    # копейки превратило бы весь дневной расход в ноль.
    return total.quantize(Decimal("0.000001"))
