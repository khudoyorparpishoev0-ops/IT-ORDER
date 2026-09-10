"""Фоновые задачи: что и когда отработало, ручной запуск.

Раздел администратора: расписание никто не видит, пока не понадобилось
проверить, ушли ли напоминания. Ручной запуск нужен ровно для этого —
дожидаться девяти утра, чтобы убедиться в настройке почты и бота,
неразумно.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, RequirePermission, bind_audit_actor
from app.core.permissions import Permission
from app.db.models import JobRun
from app.schemas.jobs import JobRunOut, JobRunResult
from app.services import jobs as svc
from app.services.audit import write_audit

manage = Depends(RequirePermission(Permission.MANAGE_REFERENCE))

router = APIRouter(
    prefix="/api/jobs",
    tags=["jobs"],
    dependencies=[Depends(bind_audit_actor), manage],
)


#: Сколько запусков берём по каждой задаче. Не общий срез по времени:
#: поиск критичных проблем идёт каждые двадцать минут и за один день
#: вытеснил бы из списка все ежедневные рассылки — а смотрят сюда как
#: раз затем, чтобы проверить, ушли ли они.
PER_JOB = 5


@router.get("", response_model=list[JobRunOut])
def list_runs(session: DbSession, limit: int = 20):
    ranked = (
        select(
            JobRun,
            func.row_number()
            .over(partition_by=JobRun.job, order_by=JobRun.started_at.desc())
            .label("rn"),
        )
        .subquery()
    )
    runs = session.scalars(
        select(JobRun)
        .join(ranked, JobRun.id == ranked.c.id)
        .where(ranked.c.rn <= PER_JOB)
        .order_by(JobRun.started_at.desc())
        .limit(limit)
    )
    return [
        JobRunOut(
            id=run.id,
            job=run.job,
            label=svc.JOB_LABEL.get(run.job, run.job),
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            details=run.details,
        )
        for run in runs
    ]


@router.post("/{job}/run", response_model=JobRunResult)
def run_job(session: DbSession, user: CurrentUser, job: str):
    """Запуск задачи сейчас, вне расписания.

    Запись в журнал действий обязательна: рассылка уходит живым людям,
    и в истории должно быть видно, кто её вызвал.
    """
    details = svc.run_now(session, job)
    write_audit(
        session,
        entity="job",
        entity_id=job,
        action="job_run",
        details=f"{svc.JOB_LABEL.get(job, job)}: {details}",
    )
    return JobRunResult(job=job, label=svc.JOB_LABEL.get(job, job), details=details)
