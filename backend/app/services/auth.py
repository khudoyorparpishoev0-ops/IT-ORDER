"""Вход, второй фактор, пароли, создание первого администратора.

Вход двухшаговый, если у сотрудника включён второй фактор:

    почта + пароль ──▶ промежуточный токен ──▶ код из приложения ──▶ сессия

Промежуточный токен живёт минуты и не даёт доступа к данным: он лишь
подтверждает, что первый фактор пройден.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.email_policy import EmailPolicyError, ensure_corporate, normalize
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.security import (
    TokenError,
    create_password_reset_token,
    hash_password,
    password_fingerprint,
    read_password_reset_token,
    needs_rehash,
    validate_password_strength,
    verify_password,
)
from app.core.time import utcnow
from app.core.totp import (
    RECOVERY_CODE_COUNT,
    TotpError,
    current_step,
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    generate_secret,
    hash_recovery_code,
    provisioning_uri,
    qr_svg,
    verify_code,
)
from app.db.models import Employee, EmployeeRole, RecoveryCode
from app.services.audit import write_audit

log = logging.getLogger(__name__)

#: Одно и то же сообщение на неизвестную почту и неверный пароль:
#: разные ответы позволяют по очереди выяснить, кто вообще заведён.
INVALID_CREDENTIALS = "Неверная почта или пароль"


class AuthError(Exception):
    """Вход не удался. → 401"""


class TwoFactorRequired(Exception):
    """Первый фактор пройден, нужен код. Не ошибка, а шаг сценария."""

    def __init__(self, employee: Employee, *, setup_required: bool = False) -> None:
        self.employee = employee
        #: true — второй фактор обязателен по роли, но ещё не настроен.
        self.setup_required = setup_required
        super().__init__("Требуется код второго фактора")


# --------------------------------------------------------------------------
# Блокировка после серии неудач
# --------------------------------------------------------------------------
def _is_locked(employee: Employee) -> bool:
    return employee.locked_until is not None and employee.locked_until > utcnow()


def _register_failure(session: Session, employee: Employee) -> None:
    """Считает неудачную попытку и при необходимости блокирует вход.

    Коммит здесь обязателен: неудачный вход завершается исключением, а
    обработчик запроса откатывает транзакцию — счётчик был бы потерян,
    и защиты от перебора не осталось бы вовсе. К этому моменту в сессии
    нет других изменений, кроме самого счётчика.
    """
    settings = get_settings()
    employee.failed_logins += 1
    # Пишем каждую неудачу: по журналу видно подбор пароля задолго до
    # блокировки. Для несуществующей почты записи нет намеренно — иначе
    # журнал забивался бы мусором с любого сканера.
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="login_failed",
        employee=employee,
        details=f"попытка {employee.failed_logins} из {settings.max_failed_logins}",
    )
    if employee.failed_logins >= settings.max_failed_logins:
        employee.locked_until = utcnow() + timedelta(minutes=settings.lockout_minutes)
        employee.failed_logins = 0
        write_audit(
            session,
            entity="employee",
            entity_id=employee.id,
            action="login_locked",
            employee=employee,
            details=f"на {settings.lockout_minutes} мин",
        )
        log.warning("Вход заблокирован для сотрудника %s", employee.id)
    session.commit()


def _reset_failures(employee: Employee) -> None:
    employee.failed_logins = 0
    employee.locked_until = None


def _lockout_message(employee: Employee) -> str:
    minutes = max(1, int((employee.locked_until - utcnow()).total_seconds() // 60) + 1)
    return (
        f"Слишком много неудачных попыток. Вход заблокирован примерно "
        f"на {minutes} мин."
    )


# --------------------------------------------------------------------------
# Первый фактор
# --------------------------------------------------------------------------
def requires_2fa(employee: Employee) -> bool:
    """Обязателен ли второй фактор этой роли."""
    return employee.role.value in get_settings().roles_requiring_2fa


def authenticate(session: Session, email: str, password: str) -> Employee:
    """Проверяет почту и пароль.

    Поднимает TwoFactorRequired, если нужен код: это не отказ, а следующий шаг.
    """
    value = normalize(email)
    employee = session.scalar(
        select(Employee).where(func.lower(Employee.email) == value)
    )

    if employee is None or not employee.password_hash:
        # Хэшируем впустую, чтобы ответ на несуществующую почту занимал
        # столько же времени, сколько на существующую.
        verify_password(password, _DUMMY_HASH)
        raise AuthError(INVALID_CREDENTIALS)

    if _is_locked(employee):
        raise AuthError(_lockout_message(employee))

    if not verify_password(password, employee.password_hash):
        _register_failure(session, employee)
        raise AuthError(INVALID_CREDENTIALS)

    rehash_if_needed(employee, password)

    if not employee.active:
        raise AuthError("Учётная запись отключена. Обратитесь к администратору.")

    # Домен проверяем и на входе: политику могли ужесточить после того,
    # как сотрудник был заведён.
    if not _domain_allowed(employee.email):
        raise AuthError(
            "Эта почта больше не относится к корпоративному домену. "
            "Обратитесь к администратору."
        )

    if employee.totp_enabled:
        raise TwoFactorRequired(employee)
    if requires_2fa(employee):
        # Роль обязана иметь второй фактор, но он не настроен: пускаем
        # только на настройку, а не в систему.
        raise TwoFactorRequired(employee, setup_required=True)

    complete_login(session, employee)
    return employee


def _domain_allowed(email: str | None) -> bool:
    from app.core.email_policy import is_corporate

    return bool(email) and is_corporate(email)


def complete_login(session: Session, employee: Employee) -> None:
    """Финальный шаг входа: отметка времени, сброс счётчика, запись в журнал."""
    employee.last_login_at = utcnow()
    _reset_failures(employee)
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="login",
        employee=employee,
        details="со вторым фактором" if employee.totp_enabled else None,
    )
    session.flush()


# --------------------------------------------------------------------------
# Второй фактор
# --------------------------------------------------------------------------
def verify_second_factor(session: Session, employee: Employee, code: str) -> Employee:
    """Проверяет код из приложения или код восстановления."""
    if _is_locked(employee):
        raise AuthError(_lockout_message(employee))
    if not employee.totp_enabled or not employee.totp_secret:
        raise AuthError("Второй фактор не настроен")

    if _try_totp(session, employee, code) or _try_recovery(session, employee, code):
        complete_login(session, employee)
        return employee

    _register_failure(session, employee)
    raise AuthError("Неверный код. Проверьте время на телефоне и попробуйте снова.")


def _try_totp(session: Session, employee: Employee, code: str) -> bool:
    secret = decrypt_secret(employee.totp_secret or "")
    if not verify_code(secret, code):
        return False

    step = current_step(secret, code)
    if step is not None and employee.totp_last_step == step:
        # Тот же код уже использован: в пределах 30-секундного окна
        # подсмотренный код иначе сработал бы второй раз.
        log.warning("Повторное использование кода TOTP, сотрудник %s", employee.id)
        return False

    employee.totp_last_step = step
    session.flush()
    return True


def _try_recovery(session: Session, employee: Employee, code: str) -> bool:
    digest = hash_recovery_code(code)
    entry = session.scalar(
        select(RecoveryCode).where(
            RecoveryCode.employee_id == employee.id,
            RecoveryCode.code_hash == digest,
            RecoveryCode.used_at.is_(None),
        )
    )
    if entry is None:
        return False

    entry.used_at = utcnow()
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="recovery_code_used",
        username=employee.full_name,
    )
    log.warning("Вход по коду восстановления, сотрудник %s", employee.id)
    session.flush()
    return True


def confirm_identity(session: Session, actor: Employee, code: str | None) -> None:
    """Требует у действующего человека код второго фактора. Иначе — отказ.

    Зачем это отдельно от входа. Сессия живёт часами: незакрытый ноутбук,
    украденная cookie, чужой человек за столом — и права администратора у
    того, кто не вводил ни одного пароля. Смена чужого пароля и сброс
    чужого второго фактора — это захват учётной записи, в том числе
    бухгалтерии, поэтому здесь мы спрашиваем ещё раз и требуем то, что
    нельзя украсть вместе с сессией: код из приложения на телефоне.

    Годится и код восстановления: телефон теряют, а доступ администратору
    нужен и в этот день.

    Без настроенного второго фактора действие не выполняется вовсе. Иначе
    подтверждение обходилось бы простым «а у меня 2FA не включён» — то
    есть не существовало бы.
    """
    if not actor.totp_enabled or not actor.totp_secret:
        raise ValidationError(
            "Включите двухфакторный вход в «Параметрах»: без него менять "
            "чужой доступ нельзя."
        )
    if _is_locked(actor):
        raise ValidationError(_lockout_message(actor))

    value = (code or "").strip().replace(" ", "")
    if not value:
        raise ValidationError("Введите код из приложения")

    if _try_totp(session, actor, value) or _try_recovery(session, actor, value):
        _reset_failures(actor)
        session.flush()
        return

    # Считаем неудачу тем же счётчиком, что и вход: шестизначный код
    # перебирается за миллион попыток, и без ограничения открытая сессия
    # администратора стала бы стендом для перебора его же кода.
    _register_failure(session, actor)
    raise ValidationError("Неверный код. Проверьте приложение на телефоне.")


def start_totp_setup(session: Session, employee: Employee) -> dict[str, str]:
    """Готовит секрет и QR. Второй фактор включится только после
    подтверждения кодом — иначе ошибка настройки заперла бы человека."""
    if not employee.email:
        raise ValidationError("У сотрудника не заполнена рабочая почта")

    secret = generate_secret()
    employee.totp_secret = encrypt_secret(secret)
    employee.totp_enabled = False
    session.flush()

    uri = provisioning_uri(secret, employee.email)
    return {
        "secret": secret,
        "uri": uri,
        "qr_svg": qr_svg(uri),
    }


def confirm_totp_setup(
    session: Session, employee: Employee, code: str
) -> list[str]:
    """Включает второй фактор и выдаёт коды восстановления."""
    if not employee.totp_secret:
        raise ConflictError("Настройка не начата: сначала получите QR-код")
    if employee.totp_enabled:
        raise ConflictError("Второй фактор уже включён")

    secret = decrypt_secret(employee.totp_secret)
    if not verify_code(secret, code):
        raise AuthError("Код не подошёл. Проверьте время на телефоне.")

    employee.totp_enabled = True
    employee.totp_confirmed_at = utcnow()
    employee.totp_last_step = current_step(secret, code)

    codes = _issue_recovery_codes(session, employee)
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="totp_enabled",
        username=employee.full_name,
    )
    session.flush()
    return codes


def _delete_recovery_codes(session: Session, employee: Employee) -> None:
    """Удаляет коды запросом, а не обходом employee.recovery_codes.

    Коллекция в памяти может быть устаревшей: коды добавляются в сессию
    напрямую, и связь их не видит. Через неё старые коды пережили бы
    перевыпуск и продолжали открывать вход.
    """
    session.execute(delete(RecoveryCode).where(RecoveryCode.employee_id == employee.id))
    session.expire(employee, ["recovery_codes"])
    session.flush()


def _issue_recovery_codes(session: Session, employee: Employee) -> list[str]:
    """Выдаёт новый комплект кодов, старые аннулирует."""
    _delete_recovery_codes(session, employee)

    codes = generate_recovery_codes(RECOVERY_CODE_COUNT)
    for code in codes:
        session.add(
            RecoveryCode(employee_id=employee.id, code_hash=hash_recovery_code(code))
        )
    session.flush()
    return codes


def regenerate_recovery_codes(
    session: Session, employee: Employee, password: str
) -> list[str]:
    """Перевыпуск кодов. Требует пароль: иначе оставленная сессия
    позволила бы выпустить себе новые коды и закрепиться."""
    if not employee.password_hash or not verify_password(
        password, employee.password_hash
    ):
        raise AuthError("Пароль указан неверно")
    if not employee.totp_enabled:
        raise ConflictError("Второй фактор не включён")

    codes = _issue_recovery_codes(session, employee)
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="recovery_codes_reissued",
        username=employee.full_name,
    )
    return codes


def disable_totp(session: Session, employee: Employee, password: str) -> None:
    """Отключение второго фактора самим сотрудником."""
    if requires_2fa(employee):
        raise ConflictError(
            "Для вашей роли второй фактор обязателен и не может быть отключён"
        )
    if not employee.password_hash or not verify_password(
        password, employee.password_hash
    ):
        raise AuthError("Пароль указан неверно")

    _clear_totp(session, employee)
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="totp_disabled",
        username=employee.full_name,
    )


def reset_totp(session: Session, employee_id: int, *, actor: str) -> Employee:
    """Сброс второго фактора администратором: сотрудник потерял телефон
    и коды восстановления. После сброса он настраивает всё заново."""
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError(f"Сотрудник {employee_id} не найден")

    _clear_totp(session, employee)
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="totp_reset_by_admin",
        username=actor,
    )
    log.warning("Администратор %s сбросил второй фактор сотруднику %s", actor, employee_id)
    return employee


def _clear_totp(session: Session, employee: Employee) -> None:
    employee.totp_enabled = False
    employee.totp_secret = None
    employee.totp_confirmed_at = None
    employee.totp_last_step = None
    _delete_recovery_codes(session, employee)


def unused_recovery_count(session: Session, employee: Employee) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(RecoveryCode)
            .where(
                RecoveryCode.employee_id == employee.id,
                RecoveryCode.used_at.is_(None),
            )
        )
        or 0
    )


# --------------------------------------------------------------------------
# Пароли
# --------------------------------------------------------------------------
def set_password(
    session: Session,
    employee_id: int,
    password: str,
    *,
    actor: str | None = None,
    action: str = "set_password",
    temporary: bool = True,
    details: str | None = None,
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
    # Пароль, выданный администратором, — временный: его знают двое.
    # Свой собственный человек уже выбрал сам, и требовать смены снова
    # незачем.
    employee.must_change_password = temporary
    _reset_failures(employee)
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action=action,
        username=actor,
        employee=employee,
        details=details,
    )
    return employee


def admin_reset_password(
    session: Session,
    *,
    admin: Employee,
    employee_id: int,
    password: str,
    code: str | None,
) -> Employee:
    """Административный сброс пароля сотрудника. Критичное действие.

    Собрано в одну функцию, потому что порядок проверок здесь и есть
    защита, а разложенный по роутеру он однажды разъедется:

    1. подтверждение личности администратора кодом второго фактора —
       одной открытой сессии недостаточно;
    2. цель существует и работает в компании: сброс уволенному только
       открывает ему дверь обратно;
    3. пароль назначается временным (`must_change_password`);
    4. все прежние сессии сотрудника гаснут — это делает смена отпечатка
       пароля в токене, отдельного шага не требуется;
    5. событие пишется в журнал с обоими именами.

    Неудачное подтверждение тоже попадает в журнал: попытка сбросить
    чужой пароль — это то, о чём владелец должен узнать, даже если она
    не удалась.
    """
    target = session.get(Employee, employee_id)
    if target is None:
        raise NotFoundError(f"Сотрудник {employee_id} не найден")

    try:
        confirm_identity(session, admin, code)
    except ValidationError as exc:
        write_audit(
            session,
            entity="employee",
            entity_id=target.id,
            action="admin_password_reset_failed",
            username=admin.full_name,
            employee=target,
            # Ни кода, ни пароля здесь нет и быть не может: в журнал идёт
            # только причина отказа.
            details=f"{target.full_name}: {exc}",
        )
        session.commit()
        raise

    if not target.active:
        raise ValidationError(
            "Сотрудник не работает в компании. Сначала верните ему доступ "
            "отметкой «Работает в компании»."
        )

    return set_password(
        session,
        target.id,
        password,
        actor=admin.full_name,
        action="admin_password_reset",
        temporary=True,
        details=f"{target.full_name}: выдан временный пароль, сеансы завершены",
    )


def change_own_password(
    session: Session, employee: Employee, current: str, new: str
) -> Employee:
    if not employee.password_hash or not verify_password(current, employee.password_hash):
        raise AuthError("Текущий пароль указан неверно")
    if current == new:
        raise ConflictError("Новый пароль совпадает со старым")
    # Отдельное действие: в журнале «сменил себе» и «выдал администратор» —
    # разные события, и разбирают их по-разному.
    return set_password(
        session,
        employee.id,
        new,
        actor=employee.full_name,
        action="password_changed",
        temporary=False,
    )


def rehash_if_needed(employee: Employee, password: str) -> None:
    """Параметры Argon2 со временем ужесточаются — обновляем хэш,
    пока пароль под рукой."""
    if employee.password_hash and needs_rehash(employee.password_hash):
        employee.password_hash = hash_password(password)
        log.info("Хэш пароля обновлён для сотрудника %s", employee.id)


# --------------------------------------------------------------------------
# Первый администратор
# --------------------------------------------------------------------------
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

    try:
        email = ensure_corporate(settings.bootstrap_admin_email)
    except EmailPolicyError as exc:
        log.error("Стартовый администратор не создан: %s", exc)
        return

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
        "Создан стартовый администратор %s. Удалите BOOTSTRAP_ADMIN_* из .env, "
        "смените пароль и настройте второй фактор после первого входа.",
        email,
    )


#: Хэш заведомо несуществующего пароля — для выравнивания времени ответа.
_DUMMY_HASH = hash_password("несуществующий пароль для выравнивания времени")


# --------------------------------------------------------------------------
# Восстановление пароля по почте
# --------------------------------------------------------------------------
def build_password_reset(session: Session, email: str) -> tuple[Employee, str] | None:
    """Готовит ссылку восстановления.

    Возвращает None, если такого адреса нет или вход по нему невозможен.
    Вызывающий в любом случае отвечает одинаково: разный ответ выдал бы,
    кто заведён в системе.
    """
    value = normalize(email)
    employee = session.scalar(
        select(Employee).where(func.lower(Employee.email) == value)
    )
    if employee is None or not employee.can_sign_in:
        return None
    if not _domain_allowed(employee.email):
        return None

    token = create_password_reset_token(
        employee.id, password_hash=employee.password_hash
    )
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="password_reset_requested",
    )
    return employee, token


def apply_password_reset(session: Session, token: str, new_password: str) -> Employee:
    """Применяет ссылку из письма и ставит новый пароль."""
    try:
        employee_id, fingerprint = read_password_reset_token(token)
    except TokenError as exc:
        raise AuthError(
            "Ссылка недействительна или устарела. Запросите восстановление заново."
        ) from exc

    employee = session.get(Employee, employee_id)
    if employee is None or not employee.active:
        raise AuthError("Учётная запись недоступна")

    if password_fingerprint(employee.password_hash) != fingerprint:
        # Пароль уже сменили — эта ссылка отработала или устарела.
        raise AuthError(
            "Ссылка уже использована. Запросите восстановление заново."
        )

    # Пароль по ссылке человек выбрал сам — требовать сменить его ещё раз
    # не за чем: временным он не является.
    set_password(
        session,
        employee.id,
        new_password,
        actor=employee.full_name,
        temporary=False,
    )
    # Блокировку снимаем: человек подтвердил доступ к почте.
    _reset_failures(employee)
    write_audit(
        session,
        entity="employee",
        entity_id=employee.id,
        action="password_reset_applied",
        username=employee.full_name,
    )
    session.flush()
    return employee


def notifiable_by_permission(session: Session, permission) -> list[Employee]:
    """Кому можно писать по этому праву: активные, с почтой и не
    отключившие уведомления о заявках."""
    from app.core.permissions import has_permission

    candidates = session.scalars(
        select(Employee).where(
            Employee.active.is_(True),
            Employee.notify_new_requests.is_(True),
            Employee.email.is_not(None),
        )
    )
    return [e for e in candidates if has_permission(e.role, permission)]


def approvers_to_notify(session: Session) -> list[Employee]:
    """Кому слать письмо о новой заявке.

    Только тем, кто вправе принимать решения и не отключил уведомления.
    """
    from app.core.permissions import Permission, has_permission

    candidates = session.scalars(
        select(Employee).where(
            Employee.active.is_(True),
            Employee.notify_new_requests.is_(True),
            Employee.email.is_not(None),
        )
    )
    return [e for e in candidates if has_permission(e.role, Permission.DECIDE_REQUEST)]
