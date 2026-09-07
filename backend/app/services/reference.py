"""Справочники: сотрудники и объекты."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.email_policy import EmailPolicyError, ensure_corporate
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.db.models import Employee, ExpenseRequest, Project
from app.schemas.reference import (
    EmployeeCreate,
    EmployeeUpdate,
    ProjectCreate,
    ProjectUpdate,
)
from app.services.audit import write_audit


# --------------------------------------------------------------------------
# Объекты
# --------------------------------------------------------------------------
def list_projects(session: Session, *, only_active: bool = False) -> list[Project]:
    stmt = select(Project).order_by(Project.name)
    if only_active:
        stmt = stmt.where(Project.active.is_(True))
    return list(session.scalars(stmt))


def get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise NotFoundError(f"Объект {project_id} не найден")
    return project


def create_project(session: Session, data: ProjectCreate) -> Project:
    if session.scalar(select(Project).where(Project.name == data.name)):
        raise ConflictError(f"Объект «{data.name}» уже существует")
    project = Project(name=data.name, active=data.active)
    session.add(project)
    session.flush()
    write_audit(session, entity="project", entity_id=project.id, action="create")
    return project


def update_project(session: Session, project_id: int, data: ProjectUpdate) -> Project:
    project = get_project(session, project_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        clash = session.scalar(
            select(Project).where(Project.name == changes["name"], Project.id != project_id)
        )
        if clash:
            raise ConflictError(f"Объект «{changes['name']}» уже существует")
    for field, value in changes.items():
        setattr(project, field, value)
    write_audit(
        session,
        entity="project",
        entity_id=project.id,
        action="update",
        details=", ".join(changes),
    )
    return project


# --------------------------------------------------------------------------
# Сотрудники
# --------------------------------------------------------------------------
def list_employees(session: Session, *, only_active: bool = False) -> list[Employee]:
    stmt = select(Employee).order_by(Employee.full_name)
    if only_active:
        stmt = stmt.where(Employee.active.is_(True))
    return list(session.scalars(stmt))


def get_employee(session: Session, employee_id: int) -> Employee:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError(f"Сотрудник {employee_id} не найден")
    return employee


def _corporate_email(email: str | None) -> str | None:
    """Проверяет и нормализует адрес. Почта — логин, поэтому личные
    ящики в систему не заводим."""
    if email is None:
        return None
    try:
        return ensure_corporate(email)
    except EmailPolicyError as exc:
        raise ValidationError(str(exc)) from exc


def create_employee(session: Session, data: EmployeeCreate) -> Employee:
    payload = data.model_dump()
    payload["email"] = _corporate_email(payload.get("email"))

    if payload["email"] and session.scalar(
        select(Employee).where(func.lower(Employee.email) == payload["email"])
    ):
        raise ConflictError(f"Сотрудник с почтой {payload['email']} уже заведён")
    employee = Employee(**payload)
    session.add(employee)
    session.flush()
    write_audit(session, entity="employee", entity_id=employee.id, action="create")
    return employee


def update_employee(session: Session, employee_id: int, data: EmployeeUpdate) -> Employee:
    employee = get_employee(session, employee_id)
    changes = data.model_dump(exclude_unset=True)
    if "email" in changes:
        changes["email"] = _corporate_email(changes["email"])
    email = changes.get("email")
    if email:
        clash = session.scalar(
            select(Employee).where(
                func.lower(Employee.email) == email, Employee.id != employee_id
            )
        )
        if clash:
            raise ConflictError(f"Сотрудник с почтой {email} уже заведён")
    for field, value in changes.items():
        setattr(employee, field, value)
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="update",
        details=", ".join(changes),
    )
    return employee


def delete_employee(session: Session, employee_id: int) -> None:
    """Удалить можно только сотрудника без заявок.

    У остальных — active=false: заявки неизменяемы и должны сохранить автора.
    """
    employee = get_employee(session, employee_id)
    has_requests = session.scalar(
        select(func.count())
        .select_from(ExpenseRequest)
        .where(ExpenseRequest.employee_id == employee_id)
    )
    if has_requests:
        raise ConflictError(
            "У сотрудника есть заявки. Отключите его через active=false, "
            "а не удаляйте — история заявок должна сохранить автора."
        )
    session.delete(employee)
    write_audit(session, entity="employee", entity_id=employee_id, action="delete")
