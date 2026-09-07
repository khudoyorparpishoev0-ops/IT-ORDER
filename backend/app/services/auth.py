"""Вход, смена пароля, создание первого администратора."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.security import (
    hash_password,
    needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.core.time import utcnow
from app.db.models import Employee, EmployeeRole
from app.services.audit import write_audit

log = logging.getLogger(__name__)

#: Одно и то же сообщение на неизвестную почту и неверный пароль:
#: разные ответы позволяют по очереди выяснить, кто вообще заведён.
INVALID_CREDENTIALS = "Неверная почта или пароль"


class AuthError(Exception):
    """Вход не удался. → 401"""


def authenticate(session: Session, email: str, password: str) -> Employee:
    employee = session.scalar(
        select(Employee).where(func.lower(Employee.email) == email.strip().lower())
    )

    if employee is None or not employee.password_hash:
        # Хэшируем впустую, чтобы ответ на несуществующую почту занимал
        # столько же времени, сколько на существующую.
        verify_password(password, _DUMMY_HASH)
        raise AuthError(INVALID_CREDENTIALS)

    if not verify_password(password, employee.password_hash):
        raise AuthError(INVALID_CREDENTIALS)

    if not employee.active:
        raise AuthError("Учётная запись отключена. Обратитесь к администратору.")

    employee.last_login_at = utcnow()
    if needs_rehash(employee.password_hash):
        # Параметры Argon2 ужесточились — обновляем хэш, пароль под рукой.
        employee.password_hash = hash_password(password)
        log.info("Хэш пароля обновлён для сотрудника %s", employee.id)

    return employee


def set_password(
    session: Session, employee_id: int, password: str, *, actor: str | None = None
) -> Employee:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError(f"Сотрудник {employee_id} не найден")
    if not employee.email:
        raise ValidationError(
            "У сотрудника не заполнена рабочая почта — она служит логином"
        )
    try:
        validate_password_strength(password)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    employee.password_hash = hash_password(password)
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="set_password",
        username=actor,
    )
    return employee


def change_own_password(
    session: Session, employee: Employee, current: str, new: str
) -> Employee:
    if not employee.password_hash or not verify_password(current, employee.password_hash):
        raise AuthError("Текущий пароль указан неверно")
    if current == new:
        raise ConflictError("Новый пароль совпадает со старым")
    return set_password(session, employee.id, new, actor=employee.full_name)


def ensure_bootstrap_admin(session: Session) -> None:
    """Создаёт первого администратора, если в базе нет ни одного.

    Без этого свежую систему некому настроить: войти нельзя, а завести
    пользователя может только тот, кто уже вошёл. Значения берутся из .env
    и после первого запуска их следует удалить оттуда.
    """
    settings = get_settings()
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return

    existing_admin = session.scalar(
        select(func.count())
        .select_from(Employee)
        .where(
            Employee.role == EmployeeRole.ADMIN,
            Employee.password_hash.is_not(None),
        )
    )
    if existing_admin:
        return

    email = settings.bootstrap_admin_email.strip().lower()
    employee = session.scalar(
        select(Employee).where(func.lower(Employee.email) == email)
    )
    if employee is None:
        employee = Employee(
            full_name=settings.bootstrap_admin_name,
            position="Администратор системы",
            email=email,
            role=EmployeeRole.ADMIN,
        )
        session.add(employee)
        session.flush()
    else:
        employee.role = EmployeeRole.ADMIN

    try:
        validate_password_strength(settings.bootstrap_admin_password)
    except ValueError as exc:
        log.error("Стартовый администратор не создан: %s", exc)
        return

    employee.password_hash = hash_password(settings.bootstrap_admin_password)
    write_audit(
        session, entity="employee", entity_id=employee.id, action="bootstrap_admin"
    )
    session.commit()
    log.warning(
        "Создан стартовый администратор %s. Удалите BOOTSTRAP_ADMIN_* из .env "
        "и смените пароль после первого входа.",
        email,
    )


#: Хэш заведомо несуществующего пароля — для выравнивания времени ответа.
_DUMMY_HASH = hash_password("несуществующий пароль для выравнивания времени")
