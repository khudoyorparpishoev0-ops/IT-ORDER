"""Выгрузки: Excel и PDF.

Отдаём готовый файл целиком, а не потоком: реестр за месяц — это десятки
строк, держать соединение открытым незачем.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import CurrentUser, DbSession, PeriodDep, RequirePermission
from app.api.routes.requests import to_detail, to_list_item
from app.core.permissions import Permission, has_permission
from app.db.models import RequestStatus
from app.services import export_excel as xlsx
from app.services import export_pdf as pdf
from app.services import reports as reports_svc
from app.services import requests as requests_svc
from app.services.reference import get_project

router = APIRouter(prefix="/api/exports", tags=["exports"])

reports_access = Depends(RequirePermission(Permission.VIEW_REPORTS))

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _attachment(content: bytes, filename: str, media_type: str) -> Response:
    """Ответ с вложением.

    Имя файла кириллическое, поэтому обязателен filename* по RFC 5987:
    в обычном filename браузеры допускают только ASCII и покажут кракозябры.
    Латинская запасная версия остаётся для старых клиентов.
    """
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    disposition = (
        f"attachment; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": disposition,
            # Выгрузка всегда свежая: кэш здесь только вредит.
            "Cache-Control": "no-store",
        },
    )


@router.get("/payments.xlsx", dependencies=[reports_access])
def payments_xlsx(
    session: DbSession, period: PeriodDep, project_id: int | None = Query(default=None)
):
    """Реестр выплат за период в Excel."""
    register = reports_svc.payments_register(
        session, year=period.year, month=period.month, project_id=project_id
    )
    project = get_project(session, project_id).name if project_id else None
    content = xlsx.payments_workbook(
        register, year=period.year, month=period.month, project=project
    )
    return _attachment(
        content,
        xlsx.export_filename(
            "Реестр-выплат", year=period.year, month=period.month, extension="xlsx"
        ),
        XLSX_TYPE,
    )


@router.get("/payments.pdf", dependencies=[reports_access])
def payments_pdf(
    session: DbSession, period: PeriodDep, project_id: int | None = Query(default=None)
):
    """Реестр выплат за период в PDF."""
    register = reports_svc.payments_register(
        session, year=period.year, month=period.month, project_id=project_id
    )
    project = get_project(session, project_id).name if project_id else None
    content = pdf.payments_pdf(
        register, year=period.year, month=period.month, project=project
    )
    return _attachment(
        content,
        xlsx.export_filename(
            "Реестр-выплат", year=period.year, month=period.month, extension="pdf"
        ),
        "application/pdf",
    )


@router.get("/requests.xlsx")
def requests_xlsx(
    session: DbSession,
    user: CurrentUser,
    period: PeriodDep,
    status_filter: RequestStatus | None = Query(default=None, alias="status"),
    project_id: int | None = Query(default=None),
    all_periods: bool = Query(default=False),
):
    """Список заявок в Excel.

    Выгружается ровно то, что роль видит в панели: сотруднику — только его
    заявки. Ограничение по автору навязывает сервер.
    """
    employee_id = (
        None if has_permission(user.role, Permission.VIEW_ALL_REQUESTS) else user.id
    )
    # Выгрузка не постраничная: пользователю нужен весь период целиком.
    items, _ = requests_svc.list_requests(
        session,
        status=status_filter,
        employee_id=employee_id,
        project_id=project_id,
        year=None if all_periods else period.year,
        month=None if all_periods else period.month,
        limit=10_000,
        offset=0,
    )
    content = xlsx.requests_workbook(
        [to_list_item(r) for r in items],
        year=period.year,
        month=period.month,
        all_periods=all_periods,
    )
    return _attachment(
        content,
        xlsx.export_filename(
            "Заявки", year=period.year, month=period.month, extension="xlsx"
        ),
        XLSX_TYPE,
    )


@router.get("/requests/{request_id}.pdf")
def request_pdf(session: DbSession, user: CurrentUser, request_id: int):
    """Одна заявка в PDF — для подшивки к авансовому отчёту."""
    from app.api.routes.requests import _ensure_can_view

    request = requests_svc.get_request(session, request_id, full=True)
    _ensure_can_view(user, request)
    detail = to_detail(session, request)
    content = pdf.request_pdf(detail)
    return _attachment(content, f"IT-HONA_{request.number}.pdf", "application/pdf")
