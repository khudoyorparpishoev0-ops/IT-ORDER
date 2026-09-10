"""Границы видимости аналитики. Проверяются ДО обращения к модели.

Право `view_reports` открывает аналитику; кому какие заявки в ней видно,
решается здесь и только здесь. Модель фильтровать нельзя: она видит
готовый блок фактов и не может расширить его вопросом — но собран этот
блок должен быть уже по правилам.

Про «разрешённые проекты руководителя». Такой связи в ORDER нет:
сотрудник не закреплён за объектом, а объект — за руководителем. Пока её
нет, мы её не выдумываем: руководитель, финансы и администратор видят
компанию целиком, и это то, как компания работает сегодня. Появится
закрепление — сузится ровно `Scope.projects`, а вызывающие не изменятся.
То же с отделами: `Scope.department_id` появится, когда появится сама
сущность, а не раньше.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.errors import NotFoundError
from app.core.permissions import Permission, has_permission
from app.db.models import Employee


@dataclass(frozen=True)
class Scope:
    """Что этому человеку видно в аналитике.

    Пустой набор в `projects` значит «все объекты», а не «ни одного»:
    ограничение — это исключение, а не норма, и по умолчанию его нет.
    """

    employee_id: int
    #: Вся компания. False — сузить по полям ниже.
    all_company: bool = True
    #: Объекты, которыми ограничен человек. Пусто — ограничения нет.
    projects: frozenset[int] = field(default_factory=frozenset)

    def allows_project(self, project_id: int | None) -> bool:
        if self.all_company or not self.projects:
            return True
        return project_id in self.projects


def for_employee(employee: Employee) -> Scope:
    """Границы видимости сотрудника.

    Право `view_reports` уже проверено роутером; здесь решается только
    ширина обзора. Без права сюда попасть нельзя — но если попадём,
    ошибёмся в сторону запрета.
    """
    if not has_permission(employee.role, Permission.VIEW_REPORTS):
        raise NotFoundError("Аналитика недоступна")
    return Scope(employee_id=employee.id, all_company=True)
