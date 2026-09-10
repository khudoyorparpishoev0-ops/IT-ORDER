"""Шаблоны заявок. Свои у каждого: чужой шаблон не находится вовсе."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CurrentUser, DbSession, bind_audit_actor
from app.db.models import Project, RequestTemplate
from app.schemas.templates import (
    TemplateApplyOut,
    TemplateIn,
    TemplateOut,
    TemplateUpdate,
)
from app.services import templates as svc

router = APIRouter(
    prefix="/api/templates",
    tags=["templates"],
    dependencies=[Depends(bind_audit_actor)],
)


def _out(session, template: RequestTemplate) -> TemplateOut:
    project = (
        session.get(Project, template.project_id)
        if template.project_id is not None
        else None
    )
    return TemplateOut(
        id=template.id,
        name=template.name,
        project_id=template.project_id,
        project_name=project.name if project else None,
        lines=svc.lines_of(template),
        usage_count=template.usage_count,
        last_used_at=template.last_used_at.isoformat() if template.last_used_at else None,
    )


@router.get("", response_model=list[TemplateOut])
def list_templates(session: DbSession, user: CurrentUser):
    return [_out(session, t) for t in svc.list_for(session, user)]


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create(session: DbSession, user: CurrentUser, data: TemplateIn):
    template = svc.create(
        session,
        user,
        name=data.name,
        lines=[line.model_dump() for line in data.lines],
        project_id=data.project_id,
    )
    session.commit()
    return _out(session, template)


@router.patch("/{template_id}", response_model=TemplateOut)
def update(session: DbSession, user: CurrentUser, template_id: int, data: TemplateUpdate):
    template = svc.update(
        session,
        user,
        template_id,
        name=data.name,
        lines=[line.model_dump() for line in data.lines] if data.lines else None,
        project_id=data.project_id,
        clear_project=data.clear_project,
    )
    session.commit()
    return _out(session, template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete(session: DbSession, user: CurrentUser, template_id: int) -> Response:
    svc.delete(session, user, template_id)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{template_id}/apply", response_model=TemplateApplyOut)
def apply(session: DbSession, user: CurrentUser, template_id: int):
    """Готовит шаблон к подстановке в форму и считает применение.

    Заявку не создаёт: подставить состав — не то же, что подать заявку.
    """
    template, warning = svc.apply(session, user, template_id)
    session.commit()
    return TemplateApplyOut(template=_out(session, template), warning=warning)
