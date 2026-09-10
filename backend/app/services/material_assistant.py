"""Помощник по материалам: проверяет написание и предлагает знакомое.

Сотрудник пишет «гофра16» — помощник предлагает «Гофра 16 мм», а если
такое уже заказывали как «Гофра гибкая 16 мм», предложит именно это
написание: тогда в отчётах и подсказках один материал не расползается
на пять вариантов. Решение остаётся за человеком — кнопка «Применить»,
молча текст не переписывается.

Модель видит каталог того, что уже заказывали (`materials_catalog`):
без него она не знала бы, как материал называют в компании.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import assistant
from app.db.models import AiKind
from app.schemas.reference import MaterialAdviceOut
from app.services import ai_log, ai_memory
from app.services.reference import materials_catalog

log = logging.getLogger(__name__)

SYSTEM = """Ты помощник по закупкам строительной и IT-компании в Таджикистане.
Сотрудник заполняет заявку на расход и пишет, какой материал ему нужен.
Твоя задача — привести название к грамотному, однозначному виду.

Правила:
1. Исправляй орфографию и регистр («гофра16» → «Гофра 16 мм»), раскрывай
   очевидные сокращения, единицы измерения пиши по ГОСТ (мм, м, шт., кг, л).
2. Если в списке уже заказанных материалов есть тот же самый предмет,
   верни ЕГО написание слово в слово и укажи это в matches_existing —
   одинаковые вещи должны называться одинаково.
3. Не выдумывай характеристики, которых человек не писал. Если названия
   недостаточно для закупки (нет размера, типа, сечения), скажи об этом
   одной короткой подсказкой в notes, а не добавляй в название.
4. Единицу измерения предлагай только когда она очевидна из названия или
   из каталога; иначе оставь null.
5. Если написание уже правильное, верни его без изменений.
6. Отвечай по-русски, коротко. Не больше двух подсказок в notes."""


class MaterialAdvice(BaseModel):
    """Ответ модели. Схема — договор: свободного текста не бывает."""

    normalized: str = Field(description="Грамотное название материала")
    unit: str | None = Field(description="Единица измерения или null")
    matches_existing: bool = Field(
        description="Название взято из списка уже заказанных материалов"
    )
    notes: list[str] = Field(description="Короткие подсказки сотруднику, до двух")


#: Кэш ответов: одно и то же слово спрашивают десятки раз в день, а
#: платить и ждать за каждый раз незачем. Ограничен по размеру.
_CACHE_LIMIT = 2000
_cache: OrderedDict[tuple[str, str], MaterialAdviceOut] = OrderedDict()


def clear_cache() -> None:
    _cache.clear()


def _build_prompt(session: Session, title: str, unit: str | None) -> str:
    known = materials_catalog(session, limit=200)
    lines = [
        f"- {name}" + (f" ({known_unit})" if known_unit else "")
        for name, known_unit, _ in known
    ]
    catalog = "\n".join(lines) if lines else "(пока пусто)"
    unit_text = unit.strip() if unit and unit.strip() else "не указана"
    return (
        "Уже заказанные материалы (название и единица):\n"
        f"{catalog}\n\n"
        f"Сотрудник написал: «{title.strip()}»\n"
        f"Единица, которую он указал: {unit_text}"
    )


def advise(session: Session, *, title: str, unit: str | None = None) -> MaterialAdviceOut:
    """Совет по одному названию. Никогда не бросает: если модель
    недоступна, отвечает `available=False`, и форма работает как раньше."""
    settings = get_settings()
    clean = " ".join(title.split())
    if not settings.assistant_enabled and assistant._transport is None:
        return MaterialAdviceOut(enabled=False, available=False, title=clean)
    if len(clean) < 3:
        return MaterialAdviceOut(enabled=True, available=True, title=clean)

    # Такую поправку уже принимали люди — спрашивать модель не за что.
    # Ответ мгновенный, бесплатный и тот же самый, что получил коллега.
    known = ai_memory.alias_for(session, clean)
    if known is not None:
        return _logged(
            session,
            MaterialAdviceOut(
                enabled=True,
                available=True,
                title=clean,
                suggested=known.canonical,
                changed=known.canonical != clean,
                unit=(unit or "").strip() or known.unit,
                matches_existing=True,
                notes=[],
            ),
            question=clean,
            duration_ms=None,
        )

    key = (clean.lower(), (unit or "").strip().lower())
    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        # Ответ из кэша человек всё равно увидел и может применить, поэтому
        # обращение пишем. Время не пишем: модель мы не ждали, и средняя
        # задержка не должна выглядеть лучше, чем она есть.
        return _logged(session, cached, question=clean, duration_ms=None)

    started = time.monotonic()
    try:
        advice = assistant.ask(
            system=SYSTEM,
            prompt=_build_prompt(session, clean, unit),
            schema=MaterialAdvice,
        )
    except assistant.AssistantError as exc:
        log.warning("Помощник по материалам не ответил: %s", exc)
        ai_log.record(
            session,
            kind=AiKind.MATERIAL,
            question=clean,
            ok=False,
            error=str(exc),
            duration_ms=_ms(started),
        )
        return MaterialAdviceOut(enabled=True, available=False, title=clean)

    normalized = " ".join(advice.normalized.split()) or clean
    result = MaterialAdviceOut(
        enabled=True,
        available=True,
        title=clean,
        suggested=normalized,
        changed=normalized != clean,
        unit=(advice.unit or "").strip() or None,
        matches_existing=advice.matches_existing,
        notes=[n.strip() for n in advice.notes if n.strip()][:2],
    )
    _cache[key] = result
    if len(_cache) > _CACHE_LIMIT:
        _cache.popitem(last=False)
    return _logged(session, result, question=clean, duration_ms=_ms(started))


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _logged(
    session: Session,
    advice: MaterialAdviceOut,
    *,
    question: str,
    duration_ms: int | None,
) -> MaterialAdviceOut:
    """Пишет обращение и возвращает совет с номером записи.

    Номер нужен кнопке «Применить»: по нему панель отмечает, что советом
    воспользовались. В кэше он не хранится — иначе двое сотрудников
    получили бы один и тот же номер чужого обращения."""
    entry_id = ai_log.record(
        session,
        kind=AiKind.MATERIAL,
        question=question,
        answer=advice.suggested or advice.title,
        duration_ms=duration_ms,
        usage=assistant.last_usage() if duration_ms is not None else None,
    )
    return advice.model_copy(update={"interaction_id": entry_id})
