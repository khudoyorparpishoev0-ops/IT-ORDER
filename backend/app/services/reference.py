"""Справочники: сотрудники и объекты."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.email_policy import EmailPolicyError, ensure_corporate
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.config import get_settings
from app.db.models import (
    Employee,
    EmployeeRole,
    ExpenseRequest,
    Project,
    RecoveryCode,
)
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
    # В пояснение кладём название: по журналу должно быть понятно, о ком
    # или о чём речь, без похода в справочник за номером.
    write_audit(
        session,
        entity="project",
        entity_id=project.id,
        action="create",
        details=project.name,
    )
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
        details=f"{project.name} · {', '.join(changes)}" if changes else project.name,
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


def _keep_one_admin(session: Session, employee: Employee, changes: dict) -> None:
    """Не даёт снять права у последнего администратора.

    Иначе справочники, пароли и роли становятся недоступны никому, и
    вернуть доступ можно только запросом к базе руками.
    """
    if employee.role is not EmployeeRole.ADMIN or not employee.active:
        return
    role = changes.get("role", employee.role)
    active = changes.get("active", employee.active)
    if role is EmployeeRole.ADMIN and active:
        return

    others = session.scalar(
        select(func.count())
        .select_from(Employee)
        .where(
            Employee.role == EmployeeRole.ADMIN,
            Employee.active.is_(True),
            Employee.id != employee.id,
        )
    )
    if not others:
        raise ConflictError(
            "Это единственный активный администратор. Назначьте администратором "
            "кого-то ещё, а потом меняйте роль или отключайте эту запись."
        )


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
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="create",
        details=employee.full_name,
    )
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
    _keep_one_admin(session, employee, changes)
    for field, value in changes.items():
        setattr(employee, field, value)
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="update",
        details=(
            f"{employee.full_name} · {', '.join(changes)}"
            if changes
            else employee.full_name
        ),
    )
    return employee


def delete_employee(session: Session, employee_id: int) -> None:
    """Удалить можно только сотрудника без заявок.

    У остальных — active=false: заявки неизменяемы и должны сохранить автора.
    """
    employee = get_employee(session, employee_id)
    _keep_one_admin(session, employee, {"active": False})
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
    name = employee.full_name
    session.delete(employee)
    write_audit(
        session,
        entity="employee",
        entity_id=employee_id,
        action="delete",
        details=name,
    )


def access_overview(session: Session) -> list[dict]:
    """Состояние доступа по всем сотрудникам — для экрана «Сотрудники».

    Неиспользованные коды восстановления считаются одним запросом с
    группировкой: по запросу на сотрудника — это N+1 на каждой отрисовке
    списка.
    """
    required = get_settings().roles_requiring_2fa
    counts = dict(
        session.execute(
            select(RecoveryCode.employee_id, func.count())
            .where(RecoveryCode.used_at.is_(None))
            .group_by(RecoveryCode.employee_id)
        ).all()
    )
    return [
        {
            "id": e.id,
            "can_sign_in": e.can_sign_in,
            "has_password": bool(e.password_hash),
            "two_factor_enabled": e.totp_enabled,
            "two_factor_required": e.role.value in required,
            "recovery_codes_left": counts.get(e.id, 0),
            "last_login_at": e.last_login_at,
            "locked_until": e.locked_until,
        }
        for e in list_employees(session)
    ]
