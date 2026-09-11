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
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import get_settings
from app.core.money import money
from app.core.time import format_local_date, format_local_datetime, utcnow
from app.db.models import RequestStatus
from app.schemas.report import PaymentsRegister
from app.services import categories
from app.services.export_excel import METHOD_LABEL, STATUS_LABEL, period_title

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
    canvas.drawString(15 * mm, 10 * mm, "IT-HONA LLC · ORDER · ВНУТРЕННИЙ ДОКУМЕНТ")
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
        author="IT-HONA LLC · ORDER",
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


# --- Заявка на оплату ----------------------------------------------------
#
# Отдельный документ, а не распечатка карточки. Его подшивают к
# авансовому отчёту, показывают директору и хранят год, поэтому он обязан
# читаться сам по себе: кто просил, что оплачиваем, для какого объекта,
# сколько, как посчитано, кто согласовал и кто заплатил.


DOC_TITLE = "ЗАЯВКА НА ОПЛАТУ"
COMPANY = "IT-HONA LLC"
SYSTEM_NAME = "ORDER"


class OrderMark(Flowable):
    """Знак ORDER: скруглённая рамка с квадратным отверстием.

    Рисуется вектором, а не картинкой: PNG в печати мылится, а файл
    иконки пришлось бы тащить в образ и держать в двух местах сразу.
    Пропорции — из `frontend/src/components/Logo.tsx`: внешний контур
    164×164 и отверстие 80×80 на одном центре, толщина кольца одинакова
    со всех сторон.
    """

    def __init__(self, size: float = 11 * mm, color=GREEN) -> None:
        super().__init__()
        self.size = size
        self.color = color

    def wrap(self, *_args) -> tuple[float, float]:
        return self.size, self.size

    def draw(self) -> None:
        c = self.canv
        k = self.size / 164.0
        c.saveState()
        c.setFillColor(self.color)
        # Кольцо — внешний скруглённый квадрат минус внутренний.
        path = c.beginPath()
        path.roundRect(0, 0, 164 * k, 164 * k, 34 * k)
        path.roundRect(42 * k, 42 * k, 80 * k, 80 * k, 12 * k)
        c.drawPath(path, stroke=0, fill=1)
        c.restoreState()


class QrCode(Flowable):
    """QR со ссылкой на карточку заявки.

    В коде только обычный адрес вида `https://order.ithona.tj/requests/17`.
    Ни токена, ни одноразовой ссылки: открывший его попадёт на экран
    входа и увидит заявку, только если имеет на неё право. QR — это
    способ быстро найти заявку с бумаги, а не обойти авторизацию.

    Рисуется модулями по матрице: вектор печатается чётко на любом
    принтере, а PNG на 300 dpi заметно замыливает края.
    """

    def __init__(self, url: str, size: float = 22 * mm) -> None:
        super().__init__()
        self.url = url
        self.size = size
        self._matrix: list[list[bool]] | None = None

    def _build(self) -> list[list[bool]]:
        if self._matrix is None:
            import qrcode

            code = qrcode.QRCode(border=0, box_size=1)
            code.add_data(self.url)
            code.make(fit=True)
            self._matrix = code.get_matrix()
        return self._matrix

    def wrap(self, *_args) -> tuple[float, float]:
        return self.size, self.size

    def draw(self) -> None:
        matrix = self._build()
        step = self.size / len(matrix)
        c = self.canv
        c.saveState()
        c.setFillColor(INK)
        for row, line in enumerate(matrix):
            for col, filled in enumerate(line):
                if filled:
                    # Ряды матрицы идут сверху вниз, а координаты PDF —
                    # снизу вверх, поэтому строка отсчитывается с конца.
                    y = self.size - (row + 1) * step
                    c.rect(col * step, y, step, step, stroke=0, fill=1)
        c.restoreState()


class _Numbered(Canvas):
    """Холст, знающий, сколько всего страниц.

    «Стр. 1 / 2» иначе не напечатать: на первой странице reportlab ещё не
    знает, сколько их выйдет. Поэтому страницы копятся, а рисуются в
    конце, когда счёт известен.
    """

    def __init__(self, *args, footer=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []
        self._footer = footer

    def showPage(self) -> None:  # noqa: N802 — имя из reportlab
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            if self._footer is not None:
                self._footer(self, self.getPageNumber(), total)
            super().showPage()
        super().save()


def _doc_styles() -> dict[str, ParagraphStyle]:
    """Размеров намеренно немного: заголовок, номер, рубрика, текст,
    подпись и итог. Больше — и документ перестаёт читаться как одно
    целое."""
    return {
        "doc_title": ParagraphStyle(
            "doc_title", fontName=SANS_BOLD, fontSize=18, leading=21, textColor=INK
        ),
        "doc_number": ParagraphStyle(
            "doc_number", fontName=MONO_BOLD, fontSize=11, leading=14, textColor=SLATE
        ),
        "company": ParagraphStyle(
            "company", fontName=SANS_BOLD, fontSize=9, leading=12, textColor=FOREST
        ),
        "rubric": ParagraphStyle(
            "rubric",
            fontName=MONO_BOLD,
            fontSize=7.5,
            leading=10,
            textColor=SLATE,
            spaceAfter=3,
        ),
        "key": ParagraphStyle(
            "key", fontName=SANS, fontSize=8.5, leading=12, textColor=SLATE
        ),
        "val": ParagraphStyle(
            "val", fontName=SANS, fontSize=9.5, leading=13, textColor=INK
        ),
        "val_strong": ParagraphStyle(
            "val_strong", fontName=SANS_BOLD, fontSize=9.5, leading=13, textColor=INK
        ),
        "val_num": ParagraphStyle(
            "val_num", fontName=MONO, fontSize=9, leading=13, textColor=INK
        ),
        "val_num_right": ParagraphStyle(
            "val_num_right",
            fontName=MONO,
            fontSize=9,
            leading=13,
            textColor=INK,
            alignment=TA_RIGHT,
        ),
        "meta": ParagraphStyle(
            "meta", fontName=MONO, fontSize=7.5, leading=11, textColor=SLATE
        ),
        "meta_right": ParagraphStyle(
            "meta_right",
            fontName=MONO,
            fontSize=7.5,
            leading=11,
            textColor=SLATE,
            alignment=TA_RIGHT,
        ),
        "status": ParagraphStyle(
            "status",
            fontName=MONO_BOLD,
            fontSize=10,
            leading=13,
            textColor=FOREST,
            alignment=TA_RIGHT,
        ),
        "step": ParagraphStyle(
            "step", fontName=MONO_BOLD, fontSize=6.5, leading=9, textColor=SLATE
        ),
        "quote": ParagraphStyle(
            "quote", fontName=SANS, fontSize=9, leading=13, textColor=INK, leftIndent=8
        ),
        "sum_label": ParagraphStyle(
            "sum_label", fontName=SANS_BOLD, fontSize=11, leading=14, textColor=INK
        ),
        "sum_value": ParagraphStyle(
            "sum_value",
            fontName=MONO_BOLD,
            fontSize=17,
            leading=20,
            textColor=INK,
            alignment=TA_RIGHT,
        ),
    }


def _rubric(text: str, st: dict) -> list:
    """Рубрика раздела с тонкой линией под ней."""
    rule = Table([[""]], colWidths=[174 * mm], rowHeights=[0.6])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LINE)]))
    return [Paragraph(text, st["rubric"]), rule, Spacer(1, 2.5 * mm)]


def _pairs(rows: list[tuple[str, str]], st: dict, *, key_width: float = 52 * mm) -> Table:
    """Блок «подпись — значение». Подписи одной колонкой: глаз идёт по
    ним сверху вниз и находит нужное, не читая всё подряд."""
    body = [
        [Paragraph(_t(key), st["key"]), Paragraph(_t(value), st["val"])]
        for key, value in rows
    ]
    table = Table(body, colWidths=[key_width, 174 * mm - key_width])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _amount_rows(rows: list[tuple[str, str]], st: dict) -> Table:
    """Статьи расхода: подпись слева, сумма справа моноширинным.

    Числа в столбик выравниваются по разряду — так видно, что 1 500,00
    больше 400,00, не вчитываясь.
    """
    body = [
        [Paragraph(_t(label), st["key"]), Paragraph(_t(value), st["val_num_right"])]
        for label, value in rows
    ]
    table = Table(body, colWidths=[120 * mm, 54 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
            ]
        )
    )
    return table


#: Знаки, которых нет ни в одном шрифте проекта. Пропущенный глиф
#: reportlab не рисует вовсе: «Душанбе → Регар» печатается как «Душанбе
#: Регар», и маршрут в документе теряется молча. Заменяем на то, что
#: шрифт умеет.
_MISSING_GLYPHS = {
    "\u2192": "—",  # →
    "\u2190": "—",  # ←
    "\u2013": "—",  # –
    "\u2022": "·",  # •
}


def _t(value) -> str:
    """Текст из данных — в абзац документа.

    Две вещи разом. Первая: `Paragraph` разбирает мини-XML, и материал с
    названием «Уголок <30мм» роняет выгрузку с ошибкой, а «Кабель <b>»
    подделывает вёрстку документа. Вторая: знак, которого нет в шрифте,
    reportlab молча не рисует, и маршрут «Душанбе → Регар» превращается
    в «Душанбе Регар».

    Поэтому всё, что пришло из заявки, проходит здесь. Наши собственные
    рубрики — тоже: помнить про исключения дороже, чем экранировать
    лишний раз.
    """
    from xml.sax.saxutils import escape

    text = "" if value is None else str(value)
    for bad, good in _MISSING_GLYPHS.items():
        text = text.replace(bad, good)
    return escape(text)


def _detail(detail, key: str) -> str:
    """Поле категории строкой. Пусто — пустая строка, а не «None»."""
    raw = (getattr(detail, "details", None) or {}).get(key)
    return "" if raw in (None, "") else str(raw)


def _money_field(detail, key: str) -> str:
    raw = (getattr(detail, "details", None) or {}).get(key)
    if raw in (None, ""):
        return ""
    try:
        return f"{money(raw)} TJS"
    except Exception:
        return ""


def _dates(detail, start: str, end: str) -> str:
    first, last = _detail(detail, start), _detail(detail, end)
    if not first and not last:
        return ""
    return f"{_ru_date(first)} — {_ru_date(last)}".strip(" —")


def _ru_date(iso: str) -> str:
    """«2026-09-11» → «11.09.2026». Не дата — оставляем как есть."""
    parts = iso.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2]}.{parts[1]}.{parts[0]}"
    return iso


def _lines_table(detail, st: dict) -> Table:
    """Смета материалов: нумерованная таблица с переносом названий.

    Заголовок повторяется на каждой странице (`repeatRows`), строка
    целиком не разрывается между страницами: половина позиции внизу
    одной страницы и половина вверху другой читается как две разные.
    """
    head = [
        Paragraph("№", st["th"]),
        Paragraph("НАИМЕНОВАНИЕ", st["th"]),
        Paragraph("КОЛ-ВО", st["th_right"]),
        Paragraph("ЕД.", st["th"]),
        Paragraph("ЦЕНА, TJS", st["th_right"]),
        Paragraph("СУММА, TJS", st["th_right"]),
    ]
    rows = [head]
    for index, line in enumerate(detail.lines, start=1):
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
                Paragraph(str(index), st["val_num"]),
                Paragraph(_t(line.title), st["td"]),
                Paragraph(str(line.quantity), st["td_num"]),
                Paragraph(_t(line.unit or "—"), st["td"]),
                Paragraph(price_cell, st["td_num"]),
                Paragraph(total_cell, st["td_num"]),
            ]
        )

    table = Table(
        rows,
        colWidths=[8 * mm, 76 * mm, 18 * mm, 16 * mm, 27 * mm, 29 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), FOREST),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _expense_block(detail, st: dict) -> list:
    """Что именно оплачиваем — своим видом для каждого расхода.

    Одна таблица на всё не годится: «Обед · 2 шт.» ничего не объясняет
    бухгалтеру, а «2 чел. × 1 день × 20,00» объясняет полностью. Поэтому
    у каждого вида расхода свой блок, а у материалов — смета.
    """
    spec = categories.spec_of(getattr(detail, "category", None))
    form = spec.form_type if spec else categories.LINES

    if form == categories.LINES:
        return [*_rubric("СОСТАВ РАСХОДА", st), _lines_table(detail, st)]

    if form == categories.PEOPLE_DAYS:
        people = _detail(detail, "people")
        days = _detail(detail, "days")
        rate = _money_field(detail, "rate")
        block = [
            *_rubric("ДЕТАЛИ РАСХОДА", st),
            _pairs(
                _filled(
                    [
                        ("Тип питания", _detail(detail, "meal_type")),
                        ("Количество человек", people),
                        ("Количество дней", days),
                        ("Стоимость на человека", rate),
                    ]
                ),
                st,
            ),
        ]
        if people and days and rate:
            block += [
                Spacer(1, 5 * mm),
                *_rubric("РАСЧЁТ", st),
                Paragraph(
                    _t(f"{people} чел. × {days} {_plural(days, 'день', 'дня', 'дней')} × {rate}"),
                    st["val_num"],
                ),
            ]
        return block

    if form == categories.TRIP:
        days = _detail(detail, "date_from") and str(
            categories.days_of(getattr(detail, "details", None) or {})
        )
        block = [
            *_rubric("КОМАНДИРОВКА", st),
            _pairs(
                _filled(
                    [
                        ("Сотрудники", _detail(detail, "staff")),
                        ("Направление", _detail(detail, "destination")),
                        ("Цель", _detail(detail, "purpose")),
                        ("Период", _dates(detail, "date_from", "date_to")),
                        ("Количество дней", days or ""),
                    ]
                ),
                st,
            ),
        ]
        articles = _filled(
            [
                ("Транспорт", _money_field(detail, "transport")),
                ("Проживание", _money_field(detail, "lodging")),
                ("Суточные", _money_field(detail, "per_diem")),
                ("Прочее", _money_field(detail, "other")),
            ]
        )
        if articles:
            block += [Spacer(1, 5 * mm), *_rubric("РАСХОДЫ", st), _amount_rows(articles, st)]
        return block

    if form == categories.ROUTE:
        return [
            *_rubric("ДОСТАВКА", st),
            _pairs(
                _filled(
                    [
                        ("Откуда", _detail(detail, "from_place")),
                        ("Куда", _detail(detail, "to_place")),
                        ("Что перевозится", _detail(detail, "what")),
                        ("Количество поездок", _detail(detail, "trips")),
                        ("Перевозчик", _detail(detail, "carrier")),
                    ]
                ),
                st,
            ),
        ]

    if form == categories.CARGO:
        origin = ", ".join(
            part
            for part in (_detail(detail, "from_country"), _detail(detail, "from_city"))
            if part
        )
        weight = _detail(detail, "weight_kg")
        volume = _detail(detail, "volume_m3")
        block = [
            *_rubric("КАРГО И ЛОГИСТИКА", st),
            _pairs(
                _filled(
                    [
                        ("Откуда", origin),
                        ("Куда", _detail(detail, "to_city")),
                        ("Груз", _detail(detail, "what")),
                        ("Вес", f"{weight} кг" if weight else ""),
                        ("Объём", f"{volume} м³" if volume else ""),
                        ("Количество мест", _detail(detail, "places")),
                    ]
                ),
                st,
            ),
        ]
        articles = _filled(
            [
                ("Карго", _money_field(detail, "cargo_cost")),
                ("Таможенные расходы", _money_field(detail, "customs")),
                ("Прочие расходы", _money_field(detail, "extra")),
            ]
        )
        if articles:
            block += [Spacer(1, 5 * mm), *_rubric("РАСЧЁТ", st), _amount_rows(articles, st)]
        return block

    if form == categories.VEHICLE:
        liters = _detail(detail, "liters")
        return [
            *_rubric("ТРАНСПОРТНЫЙ РАСХОД", st),
            _pairs(
                _filled(
                    [
                        ("Автомобиль", _detail(detail, "vehicle")),
                        ("Госномер", _detail(detail, "plate")),
                        ("Расход", _detail(detail, "kind")),
                        ("Количество", f"{liters} л" if liters else ""),
                        ("Объект или маршрут", _detail(detail, "route")),
                    ]
                ),
                st,
            ),
        ]

    if form == categories.SERVICE:
        return [
            *_rubric("УСЛУГА", st),
            _pairs(
                _filled(
                    [
                        ("Название", _detail(detail, "service")),
                        ("Исполнитель", _detail(detail, "contractor")),
                        ("Описание", _detail(detail, "description")),
                        ("Период", _detail(detail, "period")),
                    ]
                ),
                st,
            ),
        ]

    if form == categories.SUBSCRIPTION:
        return [
            *_rubric("УСЛУГА СВЯЗИ И IT", st),
            _pairs(
                _filled(
                    [
                        ("Тип", _detail(detail, "service_kind")),
                        ("Сервис или домен", _detail(detail, "account")),
                        ("Период", _detail(detail, "period")),
                        ("Дата продления", _ru_date(_detail(detail, "due_date"))),
                    ]
                ),
                st,
            ),
        ]

    return [
        *_rubric("РАСХОД", st),
        _pairs(
            _filled(
                [
                    ("Описание", _detail(detail, "description")),
                    ("Обоснование", _detail(detail, "reason")),
                ]
            ),
            st,
        ),
    ]


def _filled(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Только заполненные строки: «Госномер: —» занимает место и ничего
    не сообщает. Выдумывать недостающее тем более нельзя."""
    return [(key, value) for key, value in rows if value]


def _plural(count: str, one: str, few: str, many: str) -> str:
    try:
        number = int(count)
    except (TypeError, ValueError):
        return many
    if number % 10 == 1 and number % 100 != 11:
        return one
    if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        return few
    return many


#: Шаги согласования рубриками. Название шага, а не фраза про человека:
#: «Нигина Рахимова · Провёл оплату» — опечатка, видная каждому, а пола
#: сотрудника в ORDER нет. Имя и должность стоят строкой ниже, и кто что
#: сделал, понятно и так. То же правило, что в истории на экране.
#:
#: Комментарии сюда не попадают — у них свой раздел; просмотры тем более:
#: документ отвечает на вопрос «кто решил», а не «кто заглядывал».
_STEP_LABEL: dict[str, str] = {
    "created": "СОЗДАНИЕ ЗАЯВКИ",
    "edited": "ПРАВКА ЧЕРНОВИКА",
    "submitted": "ОТПРАВКА НА СОГЛАСОВАНИЕ",
    "need_approved": "СОГЛАСОВАНИЕ ПОТРЕБНОСТИ",
    "sourcing": "ПЕРЕДАЧА В ОТДЕЛ ЗАКУПА",
    "priced": "ОЦЕНКА ОТДЕЛОМ ЗАКУПА",
    "fulfilled": "ЗАКРЫТО СО СКЛАДА",
    "approved": "СОГЛАСОВАНИЕ СУММЫ",
    "auto_approved": "СОГЛАСОВАНИЕ СУММЫ",
    "rejected": "ОТКЛОНЕНИЕ ЗАЯВКИ",
    "moved": "ПЕРЕДАЧА ДАЛЬШЕ",
    "paid": "ОПЛАТА",
}

#: Куда именно передала система — по статусу, в который она перевела
#: заявку. «Передача дальше» ничего не сообщает тому, кто читает бумагу.
_MOVED_LABEL: dict[str, str] = {
    "sourcing": "ПЕРЕДАЧА В ОТДЕЛ ЗАКУПА",
    "priced": "ПЕРЕДАЧА РУКОВОДИТЕЛЮ",
    "approved": "ПЕРЕДАЧА В БУХГАЛТЕРИЮ",
    "paid": "СТАТУС «ОПЛАЧЕНА»",
    "fulfilled": "ЗАКРЫТИЕ ЗАЯВКИ",
}

#: Подписи ролей. Роль хранится снимком на момент действия, поэтому
#: здесь она уже правильная — переименовывать её задним числом не нужно.
_ROLE_LABEL: dict[str, str] = {
    "employee": "Сотрудник",
    "manager": "Руководитель",
    "procurement": "Отдел закупа",
    "finance": "Бухгалтерия",
    "admin": "Администратор",
}


def _step_label(event, steps) -> str:
    """Рубрика шага.

    У согласования их две: суммой оно становится только после оценки
    закупа, до неё руководитель одобряет сам расход. У системного
    перехода рубрика зависит от того, куда заявка ушла.
    """
    kind = event.kind.value
    if kind in ("approved", "auto_approved"):
        priced = any(other.kind.value == "priced" for other in steps)
        return "СОГЛАСОВАНИЕ СУММЫ" if priced else "СОГЛАСОВАНИЕ РАСХОДА"
    if kind in ("moved", "sourcing"):
        status = (getattr(event, "details", None) or {}).get("status")
        if isinstance(status, dict):
            status = status.get("to")
        return _MOVED_LABEL.get(str(status), _STEP_LABEL[kind])
    return _STEP_LABEL[kind]


def _when(value) -> str:
    """«11.09.2026, 03:31» → «11.09.2026 · 03:31»."""
    return format_local_datetime(value).replace(", ", " · ")


def _approval_block(detail, st: dict) -> list:
    """Кто и когда двигал заявку — по шагам, с именем и должностью.

    Системный переход подписан «ORDER · Системное действие»: маршрут
    выбрала система, и приписывать его человеку значит утверждать, что
    он сделал два действия вместо одного.
    """
    steps = [
        event
        for event in getattr(detail, "events", [])
        if event.kind.value in _STEP_LABEL
    ]
    if not steps:
        return []

    body: list = []
    for index, event in enumerate(steps, start=1):
        system = getattr(event, "actor_type", "human") == "system"
        who = SYSTEM_NAME if system else (event.actor or "Автор неизвестен")
        role = (
            "Системное действие"
            if system
            else _ROLE_LABEL.get(getattr(event, "actor_role", None) or "", "")
        )
        cell = [
            Paragraph(_step_label(event, steps), st["step"]),
            Paragraph(_t(who), st["val_strong"]),
        ]
        if role:
            cell.append(Paragraph(_t(role), st["key"]))
        extra = _step_extra(event)
        if extra:
            cell.append(Paragraph(_t(extra), st["val_num"]))
        note = _step_note(event)
        if note:
            cell.append(Paragraph(f"«{_t(note)}»", st["val"]))
        body.append(
            [
                Paragraph(f"{index}", st["meta"]),
                cell,
                Paragraph(_when(event.created_at), st["meta_right"]),
            ]
        )

    table = Table(body, colWidths=[8 * mm, 120 * mm, 46 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
            ]
        )
    )
    return [*_rubric("СОГЛАСОВАНИЕ", st), table]


def _step_extra(event) -> str:
    """Существенное про шаг: утверждённая сумма, документ выплаты.

    Секретов здесь быть не может: в подробностях события лежат только
    статус, суммы и состав правки — ни адресов, ни токенов туда не
    пишется вовсе.
    """
    details = getattr(event, "details", None) or {}
    parts = []
    total = details.get("amount_total")
    pair = details.get("amount")
    if isinstance(pair, dict) and pair.get("to"):
        parts.append(f"Сумма: {_tjs(pair['to'])}")
    elif total:
        parts.append(f"Сумма: {_tjs(total)}")
    if details.get("document"):
        parts.append(f"Документ: {details['document']}")
    return " · ".join(parts)


def _tjs(value: str) -> str:
    """«40,00 сомони» → «40,00 TJS». Валюта в документе одна: в шапке
    таблицы и в итоге стоит TJS, и «сомони» посреди этого читается как
    другая валюта."""
    return str(value).replace(" сомони", " TJS")


def _step_note(event) -> str:
    """Причина отказа — при самом отказе.

    Отдельным комментарием отклонение не записывается: тот же текст
    двумя строками читался бы как два разных высказывания. Значит, в
    документе его место здесь, иначе бумага не отвечает на вопрос
    «почему отказали».
    """
    if event.kind.value != "rejected":
        return ""
    return (getattr(event, "details", None) or {}).get("comment") or ""


def _comments_block(detail, st: dict) -> list:
    """Что писали люди по заявке. Нет комментариев — нет и раздела."""
    comments = [
        event
        for event in getattr(detail, "events", [])
        if event.kind.value == "commented"
    ]
    if not comments:
        return []

    body: list = []
    for index, event in enumerate(comments):
        text = (getattr(event, "details", None) or {}).get("comment") or event.text
        role = _ROLE_LABEL.get(getattr(event, "actor_role", None) or "", "")
        header = event.actor or "Автор неизвестен"
        if role:
            header = f"{header} · {role}"
        block = [
            Paragraph(_t(header), st["val_strong"]),
            Paragraph(_when(event.created_at), st["meta"]),
            Spacer(1, 1 * mm),
            Paragraph(f"«{_t(text)}»", st["quote"]),
            Spacer(1, 4 * mm),
        ]
        # Рубрика уезжает вместе с первым комментарием: заголовок в конце
        # страницы, а под ним пусто — это выглядит как потерянный текст.
        body.append(
            KeepTogether(
                [*_rubric("КОММЕНТАРИИ", st), *block] if index == 0 else block
            )
        )
    return body


def _total_block(detail, st: dict) -> Table:
    """Сумма — самый заметный элемент документа.

    Её ищут первой: бухгалтер открывает файл, чтобы понять, сколько
    платить. Прятать её в последней строке таблицы значит заставлять
    искать.
    """
    priced = getattr(detail, "priced", True)
    known = priced and detail.amount and detail.amount > 0
    value = f"{money(detail.amount)} TJS" if known else "не определена"
    label = "ИТОГО К ОПЛАТЕ" if known else "СУММА"

    table = Table(
        [[Paragraph(label, st["sum_label"]), Paragraph(value, st["sum_value"])]],
        colWidths=[100 * mm, 74 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), MIST),
                ("LINEABOVE", (0, 0), (-1, 0), 1.2, FOREST),
                ("LINEBELOW", (0, -1), (-1, -1), 1.2, FOREST),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _header(detail, st: dict, url: str) -> list:
    """Шапка: чей документ, что это и в каком он состоянии.

    Три вопроса, на которые отвечают до чтения: что за бумага, по какой
    заявке и можно ли по ней платить.
    """
    status = STATUS_LABEL.get(detail.status, detail.status.value)
    left = [
        Paragraph(COMPANY, st["company"]),
        Spacer(1, 4 * mm),
        Paragraph(DOC_TITLE, st["doc_title"]),
        Paragraph(f"№ {detail.number}", st["doc_number"]),
    ]
    right = [
        Paragraph("СТАТУС", st["meta_right"]),
        Paragraph(status.upper(), st["status"]),
        Spacer(1, 3 * mm),
        Paragraph(f"Создана: {detail.date}", st["meta_right"]),
        Paragraph(f"Сформирован: {_when(utcnow())}", st["meta_right"]),
    ]
    # QR — отдельной колонкой шапки, а не под датами. Под датами он
    # удлинял шапку на два сантиметра и сталкивал блок согласования на
    # следующий лист; своей колонкой он помещается в ту же высоту и на
    # разбивку не влияет вовсе.
    code = (
        [QrCode(url, size=20 * mm), Paragraph("Открыть", st["meta_right"])]
        if url
        else []
    )

    head = Table(
        [[OrderMark(), left, right, code]],
        # Правая колонка шире заголовка неспроста: «Сформирован:
        # 11.09.2026 · 03:46» в узкой переносится на две строки и лезет
        # на код.
        colWidths=[13 * mm, 80 * mm, 57 * mm, 24 * mm],
    )
    head.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (3, 0), (3, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (1, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    rule = Table([[""]], colWidths=[174 * mm], rowHeights=[1.4])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GREEN)]))
    return [head, Spacer(1, 4 * mm), rule, Spacer(1, 5 * mm)]


def _request_footer(number: str):
    """Подвал на каждой странице: чей документ, где искать и какая
    страница. Номер заявки повторяется здесь намеренно — листы
    расшиваются, и лист без номера теряет принадлежность."""
    base = get_settings().public_base_url.rstrip("/") or "order.ithona.tj"
    host = base.split("://")[-1]

    def draw(canvas, page: int, total: int) -> None:
        canvas.saveState()
        width, _ = canvas._pagesize
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
        canvas.setFont(MONO, 6.5)
        canvas.setFillColor(SLATE)
        canvas.drawString(
            18 * mm, 10 * mm, f"{COMPANY} · {SYSTEM_NAME} · ВНУТРЕННИЙ ДОКУМЕНТ"
        )
        canvas.drawCentredString(width / 2, 10 * mm, host)
        canvas.drawRightString(
            width - 18 * mm, 10 * mm, f"№ {number} · Стр. {page} / {total}"
        )
        canvas.restoreState()

    return draw


def request_pdf(detail) -> bytes:
    """Заявка на оплату — внутренний документ IT-HONA LLC.

    Не распечатка карточки: его подшивают к авансовому отчёту, показывают
    директору и хранят год. Поэтому он читается сам по себе — кто просил,
    что оплачиваем, для какого объекта, сколько, как посчитано, кто
    согласовал, кто определил цену и кто заплатил.

    Всё берётся из объекта, который собрал сервер: имена согласовавших,
    суммы и история приходят из базы, а не из запроса. Подменить имя
    согласовавшего через панель нельзя — панель в формировании документа
    не участвует вовсе.

    Ни адресов, ни токенов, ни кодов здесь не печатается: в подробностях
    события лежат только статус, суммы и состав правки, а IP и браузер
    ORDER не собирает вовсе.
    """
    register_fonts()
    st = {**_styles(), **_doc_styles()}

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        # Нижнее поле больше верхнего: под подвал и под дырокол, если
        # документ подшивают.
        bottomMargin=22 * mm,
        title=f"{DOC_TITLE} № {detail.number}",
        author=f"{COMPANY} · {SYSTEM_NAME}",
        subject="Внутренний документ",
    )

    spec = categories.spec_of(getattr(detail, "category", None))
    # Без PUBLIC_BASE_URL вести некуда, и код с «/requests/28» внутри
    # телефон никуда не приведёт: тогда QR просто не рисуется.
    base = get_settings().public_base_url.rstrip("/")
    url = f"{base}/requests/{detail.id}" if base else ""
    story: list = [*_header(detail, st, url)]

    story += _rubric("ОСНОВНАЯ ИНФОРМАЦИЯ", st)
    story.append(
        _pairs(
            _filled(
                [
                    ("Заявитель", detail.employee_name),
                    ("Должность", getattr(detail, "employee_position", "") or ""),
                    ("Объект", detail.project_name),
                    ("Категория", spec.name if spec else "не указана"),
                    ("Дата заявки", detail.date),
                    ("Статус", STATUS_LABEL.get(detail.status, detail.status.value)),
                ]
            ),
            st,
        )
    )
    story.append(Spacer(1, 4 * mm))

    story += _expense_block(detail, st)
    story.append(Spacer(1, 5 * mm))
    story.append(_total_block(detail, st))
    story.append(Spacer(1, 5 * mm))

    approval = _approval_block(detail, st)
    if approval:
        story += approval
        story.append(Spacer(1, 5 * mm))

    comments = _comments_block(detail, st)
    if comments:
        story += comments
        story.append(Spacer(1, 2 * mm))

    footer = _request_footer(detail.number)
    doc.build(
        story,
        canvasmaker=lambda *args, **kwargs: _Numbered(*args, footer=footer, **kwargs),
    )
    return buffer.getvalue()
