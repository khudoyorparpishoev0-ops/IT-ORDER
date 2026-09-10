"""Кто и откуда выполняет текущий запрос.

Журнал должен помнить действующего сотрудника и адрес, с которого пришёл
запрос. Тащить их параметром через все слои — значит менять сигнатуры
десятка функций ради одного поля, поэтому они живут в контексте запроса:
зависимость `bind_audit_actor` кладёт сотрудника, middleware — адрес, а
`write_audit` берёт их, если вызывающий не передал своё.

Контекст задаётся ТОЛЬКО в асинхронном коде (middleware и async-зависимость):
синхронная зависимость выполняется в отдельном потоке с копией контекста,
и запись из неё до обработчика не дошла бы.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class Actor:
    """Действующий сотрудник: id для связи, имя для чтения глазами.

    Роль — снимок на момент действия, а не ссылка на нынешнюю: закупщика
    переведут в руководители, и «Оценил заявку · Руководитель» станет
    неправдой про уже случившееся.
    """

    id: int | None
    name: str | None
    role: str | None = None


_actor: ContextVar[Actor | None] = ContextVar("audit_actor", default=None)
_ip: ContextVar[str | None] = ContextVar("audit_ip", default=None)


def set_actor(actor: Actor | None) -> None:
    _actor.set(actor)


def current_actor() -> Actor | None:
    return _actor.get()


def set_ip(ip: str | None) -> None:
    _ip.set(ip)


def current_ip() -> str | None:
    return _ip.get()
