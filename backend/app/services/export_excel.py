"""Выгрузка в Excel.

Брендбук: в Office используется только Arial — фирменные гарнитуры клиенту
не уходят. Числа кладём числами с денежным форматом, а не строками: иначе
получатель не сможет ни просуммировать столбец, ни отсортировать его.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.core.time import format_local_date, utcnow
from app.db.models import PaymentMethod, RequestStatus
from app.schemas.report import PaymentsRegister
from app.schemas.request import RequestListItem

#: Формат сомони: разделитель разрядов и две цифры после запятой.
#: Разделители берутся из настроек Excel получателя, поэтому в файле
#: пишем нейтральный шаблон.
MONEY_FORMAT = "# ##0.00"

FONT_NAME = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="0E3B21")  # Deep Forest
TOTAL_FILL = PatternFill("solid", fgColor="F5F7F5")  # Mist

_thin = Side(style="thin", color="E3E7E3")
CELL_BORDER = Border(bottom=_thin)

STATUS_LABEL: dict[RequestStatus, str] = {
    RequestStatus.DRAFT: "Черновик",
    RequestStatus.PENDING: "На утверждении",
    RequestStatus.APPROVED: "Одобрена",
    RequestStatus.PAID: "Оплачена",
    RequestStatus.REJECTED: "Отклонена",
}

METHOD_LABEL: dict[PaymentMethod, str] = {
    PaymentMethod.CARD: "На карту",
    PaymentMethod.CASH: "Наличными",
}

MONTHS = (
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)


def period_title(year: int, month: int) -> str:
    return f"{MONTHS[month - 1]} {year}"


def _write_title(ws: Worksheet, title: str, subtitle: str, width: int) -> int:
    """Заголовок отчёта и подпись с источником. Возвращает номер следующей строки.

    Брендбук: данные без источника и даты не публикуются.
    """
    ws.cell(row=1, column=1, value=title).font = Font(
        name=FONT_NAME, size=14, bold=True
    )
    ws.cell(row=2, column=1, value=subtitle).font = Font(
        name=FONT_NAME, size=9, color="5A655D"
    )
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=width)
    return 4


def _write_header(ws: Worksheet, row: int, columns: list[tuple[str, int]]) -> None:
    for index, (title, width) in enumerate(columns, start=1):
        cell = ws.cell(row=row, column=index, value=title)
        cell.font = Font(name=FONT_NAME, size=9, bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.row_dimensions[row].height = 28
    # Шапка остаётся видимой при прокрутке длинного реестра.
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def _money(ws: Worksheet, row: int, column: int, value: Decimal) -> None:
    cell = ws.cell(row=row, column=column, value=value)
    cell.number_format = MONEY_FORMAT
    cell.font = Font(name=FONT_NAME, size=10)
    cell.alignment = Alignment(horizontal="right")
    cell.border = CELL_BORDER


def _text(ws: Worksheet, row: int, column: int, value: str, *, bold: bool = False) -> None:
    cell = ws.cell(row=row, column=column, value=value)
    cell.font = Font(name=FONT_NAME, size=10, bold=bold)
    cell.alignment = Alignment(vertical="center")
    cell.border = CELL_BORDER


def _save(wb: Workbook) -> bytes:
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def payments_workbook(
    register: PaymentsRegister, *, year: int, month: int, project: str | None = None
) -> bytes:
    """Реестр выплат за период."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Реестр выплат"

    columns = [
        ("Оплачена", 14),
        ("Заявка", 12),
        ("Сотрудник", 26),
        ("Объект", 22),
        ("Сумма, TJS", 14),
        ("Способ", 14),
        ("Документ", 14),
    ]
    scope = f" · {project}" if project else ""
    row = _write_title(
        ws,
        f"Реестр выплат за {period_title(year, month)}{scope}",
        f"IT-HONA ORDER · выгружено {format_local_date(utcnow())} · {register.summary}",
        len(columns),
    )
    _write_header(ws, row, columns)

    for record in register.items:
        row += 1
        _text(ws, row, 1, record.paid_at)
        _text(ws, row, 2, record.number)
        _text(ws, row, 3, record.employee_name)
        _text(ws, row, 4, record.project_name)
        _money(ws, row, 5, record.amount)
        _text(ws, row, 6, METHOD_LABEL[record.method])
        _text(ws, row, 7, record.document)

    row += 1
    _text(ws, row, 1, "Итого выплачено", bold=True)
    for column in (2, 3, 4, 6, 7):
        ws.cell(row=row, column=column).fill = TOTAL_FILL
    _money(ws, row, 5, register.total)
    for column in range(1, len(columns) + 1):
        cell = ws.cell(row=row, column=column)
        cell.fill = TOTAL_FILL
        cell.font = Font(name=FONT_NAME, size=11, bold=True)
    ws.cell(row=row, column=5).number_format = MONEY_FORMAT

    return _save(wb)


def requests_workbook(
    items: list[RequestListItem], *, year: int, month: int, all_periods: bool = False
) -> bytes:
    """Список заявок с суммами и статусами."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Заявки"

    columns = [
        ("Заявка", 12),
        ("Дата", 12),
        ("Сотрудник", 26),
        ("Должность", 22),
        ("Объект", 22),
        ("Сумма, TJS", 14),
        ("Статус", 18),
    ]
    scope = "за всё время" if all_periods else f"за {period_title(year, month)}"
    row = _write_title(
        ws,
        f"Заявки на расходы {scope}",
        f"IT-HONA ORDER · выгружено {format_local_date(utcnow())} · "
        f"{len(items)} записей",
        len(columns),
    )
    _write_header(ws, row, columns)

    total = Decimal("0.00")
    for item in items:
        row += 1
        total += item.amount
        _text(ws, row, 1, item.number)
        _text(ws, row, 2, item.date)
        _text(ws, row, 3, item.employee_name)
        _text(ws, row, 4, item.employee_position)
        _text(ws, row, 5, item.project_name)
        _money(ws, row, 6, item.amount)
        _text(ws, row, 7, STATUS_LABEL[item.status])

    row += 1
    for column in range(1, len(columns) + 1):
        cell = ws.cell(row=row, column=column)
        cell.fill = TOTAL_FILL
        cell.font = Font(name=FONT_NAME, size=11, bold=True)
    ws.cell(row=row, column=1, value="Итого").font = Font(
        name=FONT_NAME, size=11, bold=True
    )
    # Итог по всем строкам выгрузки, включая отклонённые: это сумма
    # показанного списка, а не обязательство компании.
    _money(ws, row, 6, total)
    ws.cell(row=row, column=6).font = Font(name=FONT_NAME, size=11, bold=True)

    return _save(wb)


def export_filename(prefix: str, *, year: int, month: int, extension: str) -> str:
    """Имя файла вида IT-HONA_Реестр-выплат_2026-09.xlsx."""
    return f"IT-HONA_{prefix}_{year}-{month:02d}.{extension}"


def dated_filename(prefix: str, *, extension: str, today: date | None = None) -> str:
    day = today or utcnow().date()
    return f"IT-HONA_{prefix}_{day.isoformat()}.{extension}"
