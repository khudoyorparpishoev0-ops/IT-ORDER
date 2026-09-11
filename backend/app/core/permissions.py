"""Права ролей. Единственное место, где решается, кому что можно.

Разрешения описаны явной таблицей, а не разбросаны по роутерам: так видно
всю картину сразу и невозможно забыть закрыть новый эндпоинт.

Путь заявки: сотрудник описывает потребность без цен, MANAGER (или ADMIN)
согласует саму покупку, PROCUREMENT проверяет склад и проставляет цены,
MANAGER утверждает сумму, FINANCE проводит выплату. WAREHOUSE ведёт
склад: принимает, выдаёт и возвращает, в согласовании не участвует. Один человек не
проходит весь путь: свою заявку не согласуют и не оплачивают, а кто
одобрил — тот не платит.
"""

from __future__ import annotations

import enum

from app.db.models import EmployeeRole


class Permission(str, enum.Enum):
    """Что можно делать в системе."""

    #: Видеть чужие заявки. Без него сотрудник видит только свои.
    VIEW_ALL_REQUESTS = "view_all_requests"
    #: Подавать заявки от своего имени.
    CREATE_REQUEST = "create_request"
    #: Подавать заявку от имени другого сотрудника.
    CREATE_REQUEST_FOR_OTHERS = "create_request_for_others"
    #: Одобрять и отклонять — и потребность, и сумму.
    DECIDE_REQUEST = "decide_request"
    #: Проверять склад и проставлять цены (отдел закупа).
    SOURCE_REQUEST = "source_request"
    #: Проводить выплату.
    PAY_REQUEST = "pay_request"
    #: Сводки, отчёты, лимиты команды, бюджет.
    VIEW_REPORTS = "view_reports"
    #: Заводить и править сотрудников и объекты.
    MANAGE_REFERENCE = "manage_reference"
    #: Читать журнал действий: кто, что и когда делал в системе.
    VIEW_AUDIT = "view_audit"
    #: Видеть номенклатуру склада и остатки.
    VIEW_STOCK = "view_stock"
    #: Оформлять приход, выдачу и возврат, заводить позиции номенклатуры.
    MANAGE_STOCK = "manage_stock"
    #: Видеть закупочную стоимость и оценку запаса. Отдельно от остатка
    #: намеренно: «цемент, 40 мешков» и «запас на 32 000 сомони» — разные
    #: сведения, и второе нужно не всем, кому нужно первое.
    VIEW_STOCK_COST = "view_stock_cost"


_EMPLOYEE = frozenset({Permission.CREATE_REQUEST})

# Руководитель видит остатки, но не закупочную стоимость: решение
# «покупать или взять со склада» принимается по количеству, а цены
# раздавать автоматически незачем.
_MANAGER = _EMPLOYEE | {
    Permission.VIEW_ALL_REQUESTS,
    Permission.DECIDE_REQUEST,
    Permission.VIEW_REPORTS,
    Permission.VIEW_STOCK,
}

#: Кладовщик: принимает, выдаёт, возвращает. Заявки чужие не видит и
#: решений не принимает — это другая работа, а не урезанный закуп.
_WAREHOUSE = _EMPLOYEE | {
    Permission.VIEW_STOCK,
    Permission.MANAGE_STOCK,
    Permission.VIEW_STOCK_COST,
}

# Склад закупу оставлен: сегодня именно закуп отвечает «нашлось на
# складе», и отнять это значило бы сломать работающий путь заявки.
_PROCUREMENT = _EMPLOYEE | {
    Permission.VIEW_ALL_REQUESTS,
    Permission.SOURCE_REQUEST,
    Permission.VIEW_STOCK,
    Permission.MANAGE_STOCK,
    Permission.VIEW_STOCK_COST,
}

_FINANCE = _EMPLOYEE | {
    Permission.VIEW_ALL_REQUESTS,
    Permission.PAY_REQUEST,
    Permission.VIEW_REPORTS,
    Permission.VIEW_STOCK,
    Permission.VIEW_STOCK_COST,
}

_ADMIN = frozenset(Permission)

ROLE_PERMISSIONS: dict[EmployeeRole, frozenset[Permission]] = {
    EmployeeRole.EMPLOYEE: _EMPLOYEE,
    EmployeeRole.MANAGER: frozenset(_MANAGER),
    EmployeeRole.PROCUREMENT: frozenset(_PROCUREMENT),
    EmployeeRole.WAREHOUSE: frozenset(_WAREHOUSE),
    EmployeeRole.FINANCE: frozenset(_FINANCE),
    EmployeeRole.ADMIN: _ADMIN,
}


def permissions_for(role: EmployeeRole) -> frozenset[Permission]:
    """Права роли. Неизвестная роль не получает ничего — безопасный вариант
    по умолчанию, если в базе окажется значение из будущей версии."""
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: EmployeeRole, permission: Permission) -> bool:
    return permission in permissions_for(role)
