"""Справочники: объекты и сотрудники."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DbSession, PeriodDep
from app.schemas.reference import (
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    TeamMemberOut,
)
from app.services import reference as svc
from app.services.reports import team_overview

router = APIRouter(prefix="/api", tags=["reference"])


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(session: DbSession, only_active: bool = Query(default=False)):
    return svc.list_projects(session, only_active=only_active)


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(session: DbSession, data: ProjectCreate):
    return svc.create_project(session, data)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(session: DbSession, project_id: int, data: ProjectUpdate):
    return svc.update_project(session, project_id, data)


@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(session: DbSession, only_active: bool = Query(default=False)):
    return svc.list_employees(session, only_active=only_active)


@router.get("/employees/{employee_id}", response_model=EmployeeOut)
def get_employee(session: DbSession, employee_id: int):
    return svc.get_employee(session, employee_id)


@router.post(
    "/employees", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED
)
def create_employee(session: DbSession, data: EmployeeCreate):
    return svc.create_employee(session, data)


@router.patch("/employees/{employee_id}", response_model=EmployeeOut)
def update_employee(session: DbSession, employee_id: int, data: EmployeeUpdate):
    return svc.update_employee(session, employee_id, data)


@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT,
    # response_model=None обязателен: модуль использует отложенные аннотации,
    # и без него FastAPI строит для 204 тело ответа и падает при старте.
    response_model=None,
    response_class=Response,
)
def delete_employee(session: DbSession, employee_id: int) -> None:
    svc.delete_employee(session, employee_id)


@router.get("/team", response_model=list[TeamMemberOut])
def team(session: DbSession, period: PeriodDep):
    """Раздел «Команда»: лимиты и расход за период."""
    return team_overview(session, year=period.year, month=period.month)
