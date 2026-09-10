"""Границы видимости аналитики. Проверяются ДО обращения к модели.

Право `view_reports` открывает раздел; кому какие заявки в нём видно,
решается здесь и только здесь. Модель фильтровать нельзя: она получает
готовый блок фактов и не может расширить его вопросом — но собран этот
блок должен быть уже по правилам.

## Почему обзор привязан к `view_all_requests`

Заказчик просил не отдавать руководителю аналитику всей компании молча.
Проверка матрицы прав (10.09.2026) показала, что вопрос стоит иначе:

    manager      view_reports=True   view_all_requests=True
    finance      view_reports=True   view_all_requests=True
    admin        view_reports=True   view_all_requests=True
    procurement  view_reports=False  view_all_requests=True
    employee     view_reports=False  view_all_requests=False

Руководитель **уже** видит каждую заявку компании — в разделе «Заявки»,
в поиске, в выгрузке. Сузить одну аналитику, оставив всё остальное как
есть, значит не защитить ничего: те же цифры он соберёт руками за пять
минут. Это была бы видимость защиты, а она хуже её отсутствия — от неё
перестают искать настоящую.

Поэтому ширина обзора считается из уже существующего права, а не
задаётся заново: есть `view_all_requests` — компания целиком, нет —
только свои заявки. Захочет заказчик сузить руководителя по-настоящему —
менять надо матрицу прав, и тогда сузится и аналитика, и раздел
«Заявки», и выгрузка, все разом.

## Чего нет

Закрепления «сотрудник → объект» и «руководитель → объект» в ORDER не
существует, отделов тоже. Выдумывать их нельзя: фальшивый scope опаснее
честного широкого, потому что создаёт уверенность там, где её нет.
Появится закрепление — сузится ровно `Scope.projects`, а вызывающие не
изменятся. Ограничение записано в `BLIND_SPOTS` и показывается в разделе.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.errors import NotFoundError
from app.core.permissions import Permission, has_permission
from app.db.models import Employee


@dataclass(frozen=True)
class Scope:
    """Что этому человеку видно в аналитике."""

    employee_id: int
    #: Вся компания. False — только собственные заявки.
    all_company: bool = False
    #: Объекты, которыми ограничен человек. Пусто — ограничения по
    #: объектам нет (сегодня всегда так: закрепления в ORDER не бывает).
    projects: frozenset[int] = field(default_factory=frozenset)

    @property
    def visible_employee_id(self) -> int | None:
        """Чьи заявки показывать. None — все.

        То же правило, что у списка заявок: границу навязывает сервер, а
        не параметр запроса.
        """
        return None if self.all_company else self.employee_id

    def allows_project(self, project_id: int | None) -> bool:
        if not self.projects:
            return True
        return project_id in self.projects


def for_employee(employee: Employee) -> Scope:
    """Границы видимости сотрудника.

    Без права `view_reports` аналитики нет вовсе: роутер это уже
    проверил, но если сюда всё же попали — ошибаемся в сторону запрета.
    """
    if not has_permission(employee.role, Permission.VIEW_REPORTS):
        raise NotFoundError("Аналитика недоступна")
    return Scope(
        employee_id=employee.id,
        all_company=has_permission(employee.role, Permission.VIEW_ALL_REQUESTS),
    )


def can_see_analytics(employee: Employee) -> bool:
    """Пускать ли человека в директорский раздел. Для бота: там нет
    роутера с `RequirePermission`, а правило должно быть одно."""
    return bool(employee.active) and has_permission(
        employee.role, Permission.VIEW_REPORTS
    )
