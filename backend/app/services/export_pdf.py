"""Выгрузка в PDF.

Шрифты встроены в репозиторий (`app/assets/fonts`) и собираются скриптом
`scripts/build_pdf_fonts.py`: reportlab умеет только TTF, а системных
шрифтов в образе python:3.12-slim нет.

Оформление — по брендбуку: Manrope для текста, JetBrains Mono для чисел,
кодов и рубрик, шапка таблицы Deep Forest, только горизонтальные линии,
теней в печати нет.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.money import money
from app.core.time import format_local_date, utcnow
from app.schemas.report import PaymentsRegister
from app.services.export_excel import METHOD_LABEL, period_title

log = logging.getLogger(__name__)

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

SANS = "Manrope"
SANS_BOLD = "Manrope-Bold"
MONO = "JetBrainsMono"
MONO_BOLD = "JetBrainsMono-SemiBold"

# Палитра брендбука
FOREST = colors.HexColor("#0E3B21")
GREEN = colors.HexColor("#22A74E")
INK = colors.HexColor("#101613")
SLATE = colors.HexColor("#5A655D")
LINE = colors.HexColor("#E3E7E3")
MIST = colors.HexColor("#F5F7F5")

_registered = False


def register_fonts() -> None:
    """Регистрирует встроенные шрифты. Повторный вызов безвреден."""
    global _registered
    if _registered:
        return

    faces = {
        SANS: "Manrope-Regular.ttf",
        SANS_BOLD: "Manrope-Bold.ttf",
        MONO: "JetBrainsMono-Regular.ttf",
        MONO_BOLD: "JetBrainsMono-SemiBold.ttf",
    }
    for name, filename in faces.items():
        path = FONTS_DIR / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Нет шрифта {path}. Соберите их: python scripts/build_pdf_fonts.py"
            )
        pdfmetrics.registerFont(TTFont(name, str(path)))
    _registered = True


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title", fontName=SANS_BOLD, fontSize=16, leading=19, textColor=INK
        ),
        "source": ParagraphStyle(
            "source", fontName=SANS, fontSize=8.5, leading=12, textColor=SLATE
        ),
        "kicker": ParagraphStyle(
            "kicker",
            fontName=MONO_BOLD,
            fontSize=7,
            leading=10,
            textColor=SLATE,
            spaceAfter=4,
        ),
        "th": ParagraphStyle(
            "th", fontName=MONO_BOLD, fontSize=7, leading=9, textColor=colors.white
        ),
        "th_right": ParagraphStyle(
            "th_right",
            fontName=MONO_BOLD,
            fontSize=7,
            leading=9,
            textColor=colors.white,
            alignment=TA_RIGHT,
        ),
        "td": ParagraphStyle("td", fontName=SANS, fontSize=8.5, leading=11, textColor=INK),
        "td_mono": ParagraphStyle(
            "td_mono", fontName=MONO, fontSize=8, leading=11, textColor=INK
        ),
        "td_num": ParagraphStyle(
            "td_num",
            fontName=MONO_BOLD,
            fontSize=8,
            leading=11,
            textColor=INK,
            alignment=TA_RIGHT,
        ),
        "total": ParagraphStyle(
            "total", fontName=SANS_BOLD, fontSize=9.5, leading=12, textColor=INK
        ),
        "total_num": ParagraphStyle(
            "total_num",
            fontName=MONO_BOLD,
            fontSize=10.5,
            leading=13,
            textColor=INK,
            alignment=TA_RIGHT,
        ),
    }


def _footer(canvas, doc) -> None:
    """Номер страницы и отметка о служебном характере документа."""
    canvas.saveState()
    canvas.setFont(MONO, 7)
    canvas.setFillColor(SLATE)
    width, _ = doc.pagesize
    canvas.drawString(15 * mm, 10 * mm, "IT-HONA ORDER · ВНУТРЕННИЙ ДОКУМЕНТ")
    canvas.drawRightString(width - 15 * mm, 10 * mm, f"СТР. {canvas.getPageNumber()}")
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(15 * mm, 14 * mm, width - 15 * mm, 14 * mm)
    canvas.restoreState()


def payments_pdf(
    register: PaymentsRegister, *, year: int, month: int, project: str | None = None
) -> bytes:
    """Реестр выплат на A4 в альбомной ориентации: семь колонок в книжную
    не помещаются без переносов в каждой ячейке."""
    register_fonts()
    st = _styles()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=20 * mm,
        title=f"Реестр выплат {period_title(year, month)}",
        author="IT-HONA ORDER",
    )

    scope = f" · {project}" if project else ""
    story: list = [
        Paragraph("РЕЕСТР ВЫПЛАТ", st["kicker"]),
        Paragraph(f"Выплаты за {period_title(year, month)}{scope}", st["title"]),
        Spacer(1, 3 * mm),
        Paragraph(
            f"Источник: ORDER · выгружено {format_local_date(utcnow())} · "
            f"{register.summary}",
            st["source"],
        ),
        Spacer(1, 6 * mm),
    ]

    head = [
        Paragraph("ОПЛАЧЕНА", st["th"]),
        Paragraph("ЗАЯВКА", st["th"]),
        Paragraph("СОТРУДНИК", st["th"]),
        Paragraph("ОБЪЕКТ", st["th"]),
        Paragraph("СУММА, TJS", st["th_right"]),
        Paragraph("СПОСОБ", st["th"]),
        Paragraph("ДОКУМЕНТ", st["th"]),
    ]
    rows = [head]
    for record in register.items:
        rows.append(
            [
                Paragraph(record.paid_at, st["td_mono"]),
                Paragraph(record.number, st["td_mono"]),
                Paragraph(record.employee_name, st["td"]),
                Paragraph(record.project_name, st["td"]),
                Paragraph(money(record.amount), st["td_num"]),
                Paragraph(METHOD_LABEL[record.method], st["td"]),
                Paragraph(record.document, st["td_mono"]),
            ]
        )
    rows.append(
        [
            Paragraph("Итого выплачено", st["total"]),
            "",
            "",
            "",
            Paragraph(money(register.total), st["total_num"]),
            "",
            "",
        ]
    )

    widths = [24 * mm, 22 * mm, 52 * mm, 48 * mm, 32 * mm, 26 * mm, 30 * mm]
    table = Table(rows, colWidths=widths, repeatRows=1)
    last = len(rows) - 1
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), FOREST),
                ("BACKGROUND", (0, last), (-1, last), MIST),
                ("SPAN", (0, last), (3, last)),
                # Только горизонтальные линии — вертикальных сеток брендбук
                # не использует.
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
                ("LINEABOVE", (0, last), (-1, last), 0.8, INK),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)

    if not register.items:
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph("За период выплат не было.", st["source"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def request_pdf(detail) -> bytes:
    """Одна заявка: карточка сотрудника, состав расходов, итог, история.

    Печатается на A4 книжной: это документ для подшивки, а не таблица.
    """
    register_fonts()
    st = _styles()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=20 * mm,
        title=f"Заявка {detail.number}",
        author="IT-HONA ORDER",
    )

    story: list = [
        Paragraph(f"ЗАЯВКА НА РАСХОД · {detail.number}", st["kicker"]),
        Paragraph(detail.employee_name, st["title"]),
        Spacer(1, 2 * mm),
        Paragraph(
            f"{detail.employee_position} · объект «{detail.project_name}» · "
            f"подана {detail.date}",
            st["source"],
        ),
        Spacer(1, 6 * mm),
    ]

    # Поля категории — до сметы: у питания и командировки это и есть
    # содержание заявки, а смета под ними — одна выведенная строка.
    if getattr(detail, "details_summary", None):
        story.append(Paragraph("ПОДРОБНОСТИ РАСХОДА", st["kicker"]))
        story.append(Spacer(1, 2 * mm))
        for label, value in detail.details_summary:
            story.append(Paragraph(f"{label}: {value}", st["source"]))
        story.append(Spacer(1, 5 * mm))

    head = [
        Paragraph("ОПИСАНИЕ", st["th"]),
        Paragraph("КОЛ-ВО", st["th_right"]),
        Paragraph("ЦЕНА, TJS", st["th_right"]),
        Paragraph("СУММА, TJS", st["th_right"]),
    ]
    rows = [head]
    for line in detail.lines:
        # Строка со склада денег не стоила, неоценённая ещё не имеет цены —
        # в обоих случаях в колонках суммы стоит пояснение, а не ноль.
        if line.from_stock:
            price_cell = total_cell = "со склада"
        elif line.price is None:
            price_cell = total_cell = "не оценено"
        else:
            price_cell = money(line.price)
            total_cell = money(line.total)
        rows.append(
            [
                Paragraph(
                    f"{line.title} · {line.unit}" if line.unit else line.title, st["td"]
                ),
                Paragraph(str(line.quantity), st["td_num"]),
                Paragraph(price_cell, st["td_num"]),
                Paragraph(total_cell, st["td_num"]),
            ]
        )
    rows.append(
        [
            Paragraph("Итого к возмещению", st["total"]),
            "",
            "",
            Paragraph(money(detail.amount), st["total_num"]),
        ]
    )

    table = Table(rows, colWidths=[86 * mm, 22 * mm, 30 * mm, 36 * mm], repeatRows=1)
    last = len(rows) - 1
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), FOREST),
                ("BACKGROUND", (0, last), (-1, last), MIST),
                ("SPAN", (0, last), (2, last)),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
                ("LINEABOVE", (0, last), (-1, last), 0.8, INK),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 8 * mm))

    if detail.decision_comment:
        story.append(
            KeepTogether(
                [
                    Paragraph("РЕШЕНИЕ", st["kicker"]),
                    Paragraph(detail.decision_comment, st["td"]),
                    Spacer(1, 6 * mm),
                ]
            )
        )

    if detail.events:
        history = [Paragraph("ИСТОРИЯ", st["kicker"])]
        for event in detail.events:
            history.append(Paragraph(event.text, st["td"]))
            history.append(Paragraph(event.meta, st["source"]))
            history.append(Spacer(1, 2 * mm))
        story.append(KeepTogether(history))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
