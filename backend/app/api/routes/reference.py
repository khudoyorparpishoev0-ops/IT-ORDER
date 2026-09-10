"""Справочники: объекты и сотрудники.

Читать справочники может любой вошедший — без них не заполнить заявку.
Менять и назначать пароли — только администратор.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import (
    CurrentUser,
    DbSession,
    PeriodDep,
    RequirePermission,
    bind_audit_actor,
)
from app.config import get_settings
from app.core.errors import ValidationError
from app.core.mail import MailError, send
from app.core.permissions import Permission
from app.schemas.auth import ConfirmIn, PasswordSetIn
from app.schemas.reference import (
    AssistantStatus,
    MaterialAdviceIn,
    MaterialAdviceOut,
    EmployeeAccessOut,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    MaterialOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    TeamMemberOut,
)
from app.services import auth as auth_svc
from app.services import mail_templates as templates
from app.services import material_assistant
from app.services import reference as svc
from app.services.reports import team_overview

# Привязка действующего сотрудника — на уровне роутера: журнал должен
# заполняться сам, а не по памяти автора нового эндпоинта.
router = APIRouter(
    prefix="/api", tags=["reference"], dependencies=[Depends(bind_audit_actor)]
)

manage = Depends(RequirePermission(Permission.MANAGE_REFERENCE))
reports_access = Depends(RequirePermission(Permission.VIEW_REPORTS))


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    session: DbSession, _: CurrentUser, only_active: bool = Query(default=False)
):
    """Объекты со счётчиком заявок и расходом — по ним видно, что в работе."""
    return [
        ProjectOut(
            id=project.id,
            name=project.name,
            active=project.active,
            requests_count=count,
            spent=spent,
        )
        for project, count, spent in svc.projects_overview(
            session, only_active=only_active
        )
    ]


@router.post(
    "/projects",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[manage],
)
def create_project(session: DbSession, data: ProjectCreate):
    project = svc.create_project(session, data)
    # Новый объект ещё ни в одной заявке не участвует.
    return ProjectOut(id=project.id, name=project.name, active=project.active)


@router.patch("/projects/{project_id}", response_model=ProjectOut, dependencies=[manage])
def update_project(session: DbSession, project_id: int, data: ProjectUpdate):
    project = svc.update_project(session, project_id, data)
    session.flush()
    count, spent = svc.project_totals(session, project.id)
    return ProjectOut(
        id=project.id,
        name=project.name,
        active=project.active,
        requests_count=count,
        spent=spent,
    )


@router.get("/materials/assistant", response_model=AssistantStatus)
def assistant_status(_: CurrentUser):
    """Настроен ли помощник по материалам. Объявлен раньше `/materials`
    с параметрами — иначе слово «assistant» уйдёт в поиск по каталогу."""
    settings = get_settings()
    return AssistantStatus(
        enabled=settings.assistant_enabled,
        model=settings.assistant_model if settings.assistant_enabled else None,
    )


@router.post("/materials/advice", response_model=MaterialAdviceOut)
def material_advice(session: DbSession, _: CurrentUser, data: MaterialAdviceIn):
    """Совет по написанию материала. Открыт любому вошедшему: подсказка
    нужна тому, кто заполняет заявку. Сбой модели — не ошибка запроса."""
    return material_assistant.advise(session, title=data.title, unit=data.unit)


@router.get("/materials", response_model=list[MaterialOut])
def list_materials(
    session: DbSession,
    _: CurrentUser,
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=200, ge=1, le=500),
):
    """Подсказки для поля «что нужно» — из того, что уже заказывали.

    Открыто любому вошедшему: подсказки нужны тому, кто заполняет заявку.
    """
    return [
        MaterialOut(title=title, unit=unit, uses=uses)
        for title, unit, uses in svc.materials_catalog(
            session, search=search, limit=limit
        )
    ]


@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(
    session: DbSession, _: CurrentUser, only_active: bool = Query(default=False)
):
    return svc.list_employees(session, only_active=only_active)


@router.get(
    "/employees/access",
    response_model=list[EmployeeAccessOut],
    dependencies=[manage],
)
def employees_access(session: DbSession):
    """Состояние доступа по всем сотрудникам.

    Маршрут объявлен раньше «/employees/{employee_id}»: иначе FastAPI
    попробует разобрать «access» как номер сотрудника и ответит 422.
    """
    return svc.access_overview(session)


@router.get("/employees/{employee_id}", response_model=EmployeeOut)
def get_employee(session: DbSession, _: CurrentUser, employee_id: int):
    return svc.get_employee(session, employee_id)


@router.post(
    "/employees",
    response_model=EmployeeOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[manage],
)
def create_employee(session: DbSession, data: EmployeeCreate):
    return svc.create_employee(session, data)


@router.patch(
    "/employees/{employee_id}", response_model=EmployeeOut, dependencies=[manage]
)
def update_employee(session: DbSession, employee_id: int, data: EmployeeUpdate):
    return svc.update_employee(session, employee_id, data)


@router.put(
    "/employees/{employee_id}/password",
    response_model=EmployeeOut,
    dependencies=[manage],
)
def set_employee_password(
    session: DbSession, user: CurrentUser, employee_id: int, data: PasswordSetIn
):
    """Назначение пароля администратором — так заводят доступ новому
    сотруднику и восстанавливают забытый.

    Подтверждается кодом второго фактора самого администратора: одной
    открытой сессии для смены чужого пароля недостаточно.
    """
    auth_svc.confirm_identity(session, user, data.totp_code)
    return auth_svc.set_password(
        session, employee_id, data.password, actor=user.full_name
    )


@router.post(
    "/mail/test", status_code=status.HTTP_204_NO_CONTENT, response_model=None,
    response_class=Response, dependencies=[manage],
)
def send_test_mail(user: CurrentUser, response: Response) -> Response:
    """Проверочное письмо себе: показывает, верно ли настроен SMTP.

    Ошибку не глушим — администратор должен увидеть причину, а не гадать,
    почему письмо не пришло.
    """
    settings = get_settings()
    if not settings.mail_enabled:
        raise ValidationError(
            "Почта не настроена: заполните SMTP_HOST, SMTP_USER и SMTP_PASSWORD"
        )
    if not user.email:
        raise ValidationError("У вас не заполнена рабочая почта")

    try:
        send(templates.test_letter(to=user.email))
    except MailError as exc:
        raise ValidationError(str(exc)) from exc

    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/employees/{employee_id}/reset-2fa", response_model=EmployeeOut, dependencies=[manage]
)
def reset_employee_2fa(
    session: DbSession, user: CurrentUser, employee_id: int, data: ConfirmIn
):
    """Сброс второго фактора: сотрудник потерял телефон и коды
    восстановления. После сброса он настраивает всё заново.

    Подтверждается так же, как смена пароля. Оставить это действие без
    подтверждения значило бы не закрыть ничего: пароль сменить нельзя,
    зато второй фактор можно снести и войти по одному паролю.
    """
    auth_svc.confirm_identity(session, user, data.totp_code)
    return auth_svc.reset_totp(session, employee_id, actor=user.full_name)


@router.delete(
    "/employees/{employee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # response_model=None обязателен: модуль использует отложенные аннотации,
    # и без него FastAPI строит для 204 тело ответа и падает при старте.
    response_model=None,
    response_class=Response,
    dependencies=[manage],
)
def delete_employee(session: DbSession, employee_id: int) -> None:
    svc.delete_employee(session, employee_id)


@router.get("/team", response_model=list[TeamMemberOut], dependencies=[reports_access])
def team(session: DbSession, period: PeriodDep):
    """Раздел «Команда»: лимиты и расход за период."""
    return team_overview(session, year=period.year, month=period.month)
