"""Шаблоны заявок: повторяющееся дело в одно нажатие.

«Заправка Opel», «Обед сотрудников», «UTP Cat6 на Регар» — заявки, которые
подают каждую неделю одними и теми же словами. Каждый раз набирать их
заново незачем.

Шаблон принадлежит человеку, а не компании. Общий список пришлось бы
кому-то вести и чистить, а повторяющиеся дела у каждого свои: у мастера
цемент, у водителя заправка. Чужой шаблон не находится вовсе — как чужая
заявка.

Заводит шаблон только человек. Помощник может предложить сохранить
(«вы уже третий раз подаёте такую заявку»), но сам не создаёт: молча
заведённый шаблон — это список, который никто не просил.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.time import utcnow
from app.db.models import Employee, Project, RequestTemplate
from app.services.audit import write_audit

log = logging.getLogger(__name__)

#: Сколько шаблонов держим на человека. Двадцать повторяющихся дел — это
#: уже не шаблоны, а справочник, и искать в нём дольше, чем набрать.
MAX_PER_EMPLOYEE = 20

#: Сколько позиций в шаблоне. Столько же, сколько в форме заявки.
MAX_LINES = 30


def _clean_lines(lines: list[dict]) -> list[dict]:
    """Позиции шаблона в том же виде, в каком их ждёт форма заявки."""
    result = []
    for line in lines[:MAX_LINES]:
        title = " ".join(str(line.get("title") or "").split())[:200]
        if not title:
            continue
        try:
            quantity = max(1, int(line.get("quantity") or 1))
        except (TypeError, ValueError):
            quantity = 1
        unit = str(line.get("unit") or "").strip()[:32] or None
        result.append({"title": title, "quantity": quantity, "unit": unit})
    if not result:
        raise ValidationError("В шаблоне нет ни одной позиции")
    return result


def _project_for(session: Session, project_id: int | None) -> Project | None:
    if project_id is None:
        return None
    project = session.get(Project, project_id)
    if project is None:
        raise NotFoundError("Объект не найден")
    return project


def list_for(session: Session, employee: Employee) -> list[RequestTemplate]:
    """Шаблоны человека, самые ходовые сверху.

    Порядок по числу применений, а не по алфавиту: шаблон нужен, чтобы
    нажать не глядя, и то, чем пользуются каждый день, должно быть первым.
    """
    return list(
        session.scalars(
            select(RequestTemplate)
            .where(RequestTemplate.employee_id == employee.id)
            .order_by(
                RequestTemplate.usage_count.desc(),
                RequestTemplate.last_used_at.desc().nullslast(),
                RequestTemplate.name,
            )
        )
    )


def get_own(session: Session, employee: Employee, template_id: int) -> RequestTemplate:
    """Шаблон человека. Чужой — 404, как чужая заявка: иначе перебором
    номеров видно, сколько шаблонов у коллег и есть ли они вообще."""
    template = session.get(RequestTemplate, template_id)
    if template is None or template.employee_id != employee.id:
        raise NotFoundError("Шаблон не найден")
    return template


def create(
    session: Session,
    employee: Employee,
    *,
    name: str,
    lines: list[dict],
    project_id: int | None = None,
) -> RequestTemplate:
    name = " ".join((name or "").split())[:200]
    if not name:
        raise ValidationError("У шаблона должно быть название")

    count = session.scalar(
        select(func.count())
        .select_from(RequestTemplate)
        .where(RequestTemplate.employee_id == employee.id)
    )
    if count and count >= MAX_PER_EMPLOYEE:
        raise ConflictError(
            f"Шаблонов уже {MAX_PER_EMPLOYEE}. Удалите ненужные — искать в "
            "длинном списке дольше, чем набрать заявку заново."
        )

    taken = session.scalar(
        select(RequestTemplate).where(
            RequestTemplate.employee_id == employee.id, RequestTemplate.name == name
        )
    )
    if taken is not None:
        raise ConflictError(f"Шаблон «{name}» у вас уже есть")

    project = _project_for(session, project_id)
    template = RequestTemplate(
        employee_id=employee.id,
        name=name,
        project_id=project.id if project else None,
        payload={"lines": _clean_lines(lines)},
    )
    session.add(template)
    session.flush()
    write_audit(
        session,
        entity="template",
        entity_id=template.id,
        action="template_created",
        details=name,
    )
    return template


def update(
    session: Session,
    employee: Employee,
    template_id: int,
    *,
    name: str | None = None,
    lines: list[dict] | None = None,
    project_id: int | None = None,
    clear_project: bool = False,
) -> RequestTemplate:
    template = get_own(session, employee, template_id)

    if name is not None:
        clean = " ".join(name.split())[:200]
        if not clean:
            raise ValidationError("У шаблона должно быть название")
        template.name = clean
    if lines is not None:
        template.payload = {"lines": _clean_lines(lines)}
    if clear_project:
        template.project_id = None
    elif project_id is not None:
        project = _project_for(session, project_id)
        template.project_id = project.id if project else None

    template.updated_at = utcnow()
    session.flush()
    write_audit(
        session,
        entity="template",
        entity_id=template.id,
        action="template_updated",
        details=template.name,
    )
    return template


def delete(session: Session, employee: Employee, template_id: int) -> None:
    template = get_own(session, employee, template_id)
    name = template.name
    write_audit(
        session,
        entity="template",
        entity_id=template.id,
        action="template_deleted",
        details=name,
    )
    session.delete(template)
    session.flush()


def apply(
    session: Session, employee: Employee, template_id: int
) -> tuple[RequestTemplate, str | None]:
    """Готовит шаблон к подстановке в форму и считает применение.

    Заявку не создаёт: подставить состав — не то же самое, что подать
    заявку. Последнее нажатие остаётся за человеком, как и везде в ORDER.

    Второе значение — предупреждение, если объект шаблона больше не
    работает. Молча подставлять отключённый объект нельзя: заявка на него
    не подастся, а человек не поймёт почему.
    """
    template = get_own(session, employee, template_id)
    warning = None

    if template.project_id is not None:
        project = session.get(Project, template.project_id)
        if project is None or not project.active:
            warning = (
                f"Объект «{project.name}» отключён — выберите другой."
                if project
                else "Объект шаблона удалён — выберите другой."
            )
            # Ссылку снимаем прямо здесь: шаблон, который каждый раз
            # подставляет нерабочий объект, будет мешать до бесконечности.
            template.project_id = None

    template.usage_count += 1
    template.last_used_at = utcnow()
    session.flush()
    return template, warning


def lines_of(template: RequestTemplate) -> list[dict]:
    """Позиции шаблона. Форма та же, что у формы заявки."""
    payload = template.payload or {}
    return list(payload.get("lines") or [])
