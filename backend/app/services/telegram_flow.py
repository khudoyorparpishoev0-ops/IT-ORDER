"""Создание заявки из Telegram: разговор с ботом и его состояние.

Зачем. На стройке телефон под рукой, а панель — нет: мастер стоит на
объекте, и открывать браузер, чтобы попросить два мешка цемента, он не
станет. Заявка, которую не подали, — это купленный за свои материал и
испорченный отчёт.

Как. Бот ведёт короткий разговор: объект → что нужно → уточнения → карточка
подтверждения. Разбирает текст тот же помощник, что и в панели
(`request_assistant`), поэтому правила у них одни. Создаёт заявку тоже
только `services/requests.py`: второго пути создания заявки в системе нет
и не будет — иначе однажды правила разойдутся, и никто не поймёт почему.

Права те же, что в панели: роль перечитывается из базы на каждом
сообщении, отключённому сотруднику бот отказывает, заявку за другого
через бота подать нельзя.

Заявка не уходит без подтверждения: последнее нажатие всегда за
человеком, как и кнопка «Применить» в панели.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.permissions import Permission, has_permission
from app.core.text import plural
from app.core.time import utcnow
from app.db.models import (
    AiSource,
    Employee,
    ExpenseRequest,
    Project,
    RequestStatus,
    TelegramSession,
)
from app.schemas.assistant import AssistantContext, AssistantFormLine, AssistantTurn
from app.schemas.request import ExpenseLineIn, RequestCreate
from app.services import ai_memory, ai_privacy, request_assistant
from app.services import templates as templates_svc
from app.services import requests as requests_svc
from app.services.notifications import panel_url, request_url
from app.services.requests import awaiting_label, title_of

log = logging.getLogger(__name__)

#: Шаги разговора.
STEP_PROJECT = "PROJECT"
STEP_NEED = "NEED"
STEP_CLARIFY = "CLARIFY"
STEP_CONFIRM = "CONFIRM"
#: Показали ленту вариантов (частое, шаблоны, повтор) и ждём выбора.
STEP_PICK = "PICK"

#: Незаконченный разговор живёт сутки. Заявка, которую начали вчера и
#: бросили, сегодня уже про другое.
TTL_HOURS = 24

#: Сколько объектов показываем кнопками. Больше — список не читается, и
#: проще выбрать в панели.
PROJECT_LIMIT = 20

#: Сколько реплик помним. Столько же, сколько в панели.
MAX_HISTORY = 12

#: Коды кнопок. Короткие: Telegram отдаёт не больше 64 байт.
PICK_PROJECT = "p:"
PICK_OPTION = "o:"
PICK_TEMPLATE = "t:"
PICK_MATERIAL = "m:"
PICK_REPEAT = "r:"
CONFIRM_SEND = "send"
CONFIRM_EDIT = "edit"
CONFIRM_CANCEL = "cancel"
MENU_NEW = "menu:new"
MENU_LAST = "menu:last"
MENU_FREQUENT = "menu:frequent"
MENU_ACTIVE = "menu:active"
MENU_AI = "menu:ai"

#: Сколько частых материалов показываем кнопками. Больше восьми список
#: перестаёт читаться на экране телефона.
FREQUENT_LIMIT = 8

#: Сколько заявок показываем в «последних» и «моих активных».
LIST_LIMIT = 5

#: Заявка ещё в работе: по ней чего-то ждут. Оплаченная, отклонённая и
#: закрытая складом — уже нет.
IN_WORK = (
    RequestStatus.PENDING,
    RequestStatus.SOURCING,
    RequestStatus.PRICED,
    RequestStatus.APPROVED,
)

#: Ответ на просьбу подать заявку за другого. Через бота это невозможно
#: по замыслу: в панели такое право есть только у администратора, и
#: открывать его в чате, где нельзя проверить, кто пишет, нельзя.
FOREIGN_REQUEST = (
    "Через Telegram заявку можно оформить только от вашего имени."
)

#: Как человек просит подать заявку за другого. Ловим до модели: тратить
#: на это запрос к Claude незачем, а ответ всё равно один.
FOREIGN_MARKERS = (
    "за ивано", "от имени", "вместо ", "за сотрудник", "за коллег",
    "за него", "за неё", "за нее", "заявку за ", "заявка за ",
)


@dataclass
class Reply:
    """Что бот отвечает: текст, кнопки выбора и, может быть, ссылка."""

    text: str
    choices: list[tuple[str, str]] = field(default_factory=list)
    button: tuple[str, str] | None = None


NO_RIGHT = Reply(
    "Подавать заявки может не каждая роль. Если это ошибка — напишите "
    "администратору системы."
)
NO_PROJECTS = Reply(
    "Объекты не заведены — без объекта заявку не подать. Их создаёт "
    "администратор в разделе «Объекты»."
)
LOST = Reply(
    "Разговор потерялся. Начните заново командой /new."
)
CANCELLED = Reply("Отменил. Ничего не подано. Новая заявка — /new.")


# --- Состояние разговора ------------------------------------------------------


def _load(session: Session, employee: Employee) -> TelegramSession | None:
    """Текущий разговор сотрудника. Протухший считается отсутствующим."""
    session.execute(
        delete(TelegramSession).where(
            TelegramSession.created_at < utcnow() - timedelta(hours=TTL_HOURS)
        )
    )
    return session.scalar(
        select(TelegramSession).where(TelegramSession.employee_id == employee.id)
    )


def _save(
    session: Session, employee: Employee, *, step: str, data: dict
) -> TelegramSession:
    """Кладёт шаг и накопленное. Один сотрудник — один разговор."""
    existing = session.scalar(
        select(TelegramSession).where(TelegramSession.employee_id == employee.id)
    )
    if existing is None:
        existing = TelegramSession(employee_id=employee.id, step=step, data=data)
        session.add(existing)
    else:
        existing.step = step
        existing.data = data
        existing.updated_at = utcnow()
    session.flush()
    return existing


def forget(session: Session, employee: Employee) -> None:
    session.execute(
        delete(TelegramSession).where(TelegramSession.employee_id == employee.id)
    )


# --- Шаги ---------------------------------------------------------------------


def start(session: Session, employee: Employee) -> Reply:
    """`/new`: начинаем заново и спрашиваем объект."""
    if not has_permission(employee.role, Permission.CREATE_REQUEST):
        return NO_RIGHT

    projects = list(
        session.scalars(
            select(Project)
            .where(Project.active.is_(True))
            .order_by(Project.name)
            .limit(PROJECT_LIMIT)
        )
    )
    if not projects:
        return NO_PROJECTS

    forget(session, employee)
    _save(session, employee, step=STEP_PROJECT, data={"lines": [], "history": []})
    return Reply(
        "Новая заявка. На какой объект?",
        choices=[(p.name, f"{PICK_PROJECT}{p.id}") for p in projects],
    )


def pick_project(session: Session, employee: Employee, project_id: int) -> Reply:
    state = _load(session, employee)
    if state is None:
        return LOST

    project = session.get(Project, project_id)
    if project is None or not project.active:
        return Reply("Такого объекта нет или он отключён. Начните заново: /new.")

    data = dict(state.data)
    data["project_id"] = project.id
    data["project_name"] = project.name
    _save(session, employee, step=STEP_NEED, data=data)
    return Reply(
        f"Объект: <b>{project.name}</b>.\n\n"
        "Что нужно? Напишите словами, как есть: «два мешка цемента и песок», "
        "«кабель на камеры». Цены указывать не надо — их поставит закуп."
    )


def handle_text(session: Session, employee: Employee, text: str) -> Reply:
    """Свободный текст сотрудника на шаге «что нужно» или «уточнение»."""
    state = _load(session, employee)
    if state is None or state.step not in (STEP_NEED, STEP_CLARIFY):
        return LOST

    if is_for_someone_else(text):
        # Отвечаем сами, не спрашивая модель: ответ один и тот же, а
        # запрос к Claude стоит денег и секунд.
        return Reply(
            f"{FOREIGN_REQUEST}\n\nЧто нужно вам? Напишите словами."
        )

    data = dict(state.data)
    history = [AssistantTurn(**turn) for turn in data.get("history", [])][-MAX_HISTORY:]
    context = AssistantContext(
        employee_name=employee.full_name,
        employee_id=employee.id,
        project_id=data.get("project_id"),
        project_name=data.get("project_name"),
        lines=[AssistantFormLine(**line) for line in data.get("lines", [])],
    )

    reply = request_assistant.converse(
        session, text=text, history=history, context=context, source=AiSource.TELEGRAM
    )
    if not reply.available:
        # Модель молчит — не тупик: записываем сказанное строкой и
        # спрашиваем количество сами. Без помощника бот проще, но живой.
        return _simple_line(session, employee, data, text)

    data["history"] = [
        *[t.model_dump() for t in history],
        {"role": "user", "text": text},
        {"role": "assistant", "text": reply.message},
    ][-MAX_HISTORY:]

    if reply.lines:
        data["lines"] = [line.model_dump() for line in reply.lines]
        _save(session, employee, step=STEP_CONFIRM, data=data)
        return _card(data, note=reply.message)

    question = reply.questions[0] if reply.questions else None
    # Варианты последнего вопроса держим в разговоре: кнопка возвращает
    # только свой номер, а во что он превращается — знаем мы, не Telegram.
    data["options"] = list(question.options) if question else []
    _save(session, employee, step=STEP_CLARIFY, data=data)
    if question is None:
        return Reply(reply.message or "Расскажите подробнее, что нужно.")
    return Reply(
        f"{reply.message}\n\n<b>{question.question}</b>" if reply.message else question.question,
        choices=[(o, f"{PICK_OPTION}{i}") for i, o in enumerate(question.options)],
    )


def pick_option(session: Session, employee: Employee, index: int) -> Reply:
    """Нажали кнопку с готовым вариантом ответа."""
    state = _load(session, employee)
    if state is None or state.step != STEP_CLARIFY:
        return LOST

    options = list(state.data.get("options") or [])
    if index >= len(options):
        # Кнопка от прошлого вопроса: сообщение в Telegram остаётся на
        # экране навсегда, и нажать её могут через час.
        return Reply("Этот вариант уже не подходит. Напишите ответ словами.")
    return handle_text(session, employee, options[index])


def confirm(session: Session, employee: Employee) -> Reply:
    """«Отправить»: создаём заявку тем же сервисом, что и панель."""
    state = _load(session, employee)
    if state is None or state.step != STEP_CONFIRM:
        return LOST

    # Право проверяем ещё раз, у самой подачи: разговор мог начаться
    # вчера, а роль с тех пор понизили.
    if not has_permission(employee.role, Permission.CREATE_REQUEST) or not employee.active:
        forget(session, employee)
        return NO_RIGHT

    data = state.data
    lines = [
        ExpenseLineIn(
            title=line["title"],
            quantity=max(1, int(line.get("quantity") or 1)),
            unit=(line.get("unit") or None),
        )
        for line in data.get("lines", [])
        if (line.get("title") or "").strip()
    ]
    if not lines or not data.get("project_id"):
        forget(session, employee)
        return LOST

    request = requests_svc.create_request(
        session,
        RequestCreate(
            employee_id=employee.id,
            project_id=int(data["project_id"]),
            lines=lines,
            submit=True,
        ),
    )
    forget(session, employee)
    session.flush()
    return Reply(
        f"Заявка <b>{request.number}</b> подана.\n\n"
        f"Объект: {data.get('project_name')}\n"
        f"{_lines_text(data.get('lines', []))}\n\n"
        "Что дальше: руководитель согласует покупку, потом закуп поставит цены. "
        "Обо всех шагах напишу сюда.",
        button=("Открыть заявку", request_url(request)),
    )


def edit(session: Session, employee: Employee) -> Reply:
    """«Изменить»: возвращаемся к разговору, набранное остаётся."""
    state = _load(session, employee)
    if state is None:
        return LOST
    _save(session, employee, step=STEP_CLARIFY, data=dict(state.data))
    return Reply(
        "Что поправить? Напишите словами: «песка не два, а три мешка», "
        "«убери перчатки», «добавь грунтовку»."
    )


def cancel(session: Session, employee: Employee) -> Reply:
    forget(session, employee)
    return CANCELLED


def in_dialogue(session: Session, employee: Employee) -> bool:
    """Идёт ли сейчас разговор о заявке. Нужно, чтобы обычный текст не
    принимали за команду, когда человек отвечает боту."""
    return _load(session, employee) is not None


# --- Вспомогательное ----------------------------------------------------------


def _simple_line(session: Session, employee: Employee, data: dict, text: str) -> Reply:
    """Путь без модели: что написали, то и позиция.

    Сбой помощника не должен закрывать бота: заявку человек подать
    сможет, просто без разбора текста. Количество и единицу он поправит
    в панели — заявка ещё черновиком не станет, она уйдёт на согласование
    как есть.
    """
    title = " ".join(text.split())[:200]
    if not title:
        return Reply("Напишите, что нужно.")
    lines = [*data.get("lines", []), {"title": title, "quantity": 1, "unit": None}]
    data["lines"] = lines
    _save(session, employee, step=STEP_CONFIRM, data=data)
    return _card(
        data,
        note="Помощник сейчас недоступен, записал как есть — проверьте количество.",
    )


def _card(data: dict, *, note: str = "") -> Reply:
    """Карточка подтверждения. Последнее нажатие — за человеком."""
    head = note.strip() + "\n\n" if note.strip() else ""
    return Reply(
        f"{head}<b>Проверьте заявку</b>\n\n"
        f"Объект: {data.get('project_name', '—')}\n"
        f"{_lines_text(data.get('lines', []))}\n\n"
        "Цены поставит закуп — их указывать не нужно.",
        choices=[
            ("Отправить на согласование", CONFIRM_SEND),
            ("Изменить", CONFIRM_EDIT),
            ("Отмена", CONFIRM_CANCEL),
        ],
    )


def _lines_text(lines: list[dict]) -> str:
    if not lines:
        return "Позиций пока нет."
    rows = []
    for line in lines:
        amount = line.get("quantity") or 1
        unit = f" {line['unit']}" if line.get("unit") else ""
        purpose = f" — {line['purpose']}" if line.get("purpose") else ""
        rows.append(f"• {line.get('title', '')} — {amount}{unit}{purpose}")
    return "\n".join(rows)


def is_for_someone_else(text: str) -> bool:
    """Просят ли подать заявку за другого сотрудника.

    Через бота это невозможно по замыслу: в панели право подать заявку за
    другого есть только у администратора, а в чате нельзя убедиться, что
    пишет именно тот, чей это телефон. Проверка грубая и намеренно
    такая: ошибиться в сторону отказа безопаснее, чем создать заявку не
    от того имени.
    """
    low = " " + " ".join((text or "").lower().split()) + " "
    return any(marker in low for marker in FOREIGN_MARKERS)


def menu(employee: Employee) -> Reply:
    """Быстрые действия после /start и /help.

    Пять частых дел кнопками: набирать команды с телефона на стройке
    неудобно, а «Новая заявка» и «Часто заказываю» — это девять
    обращений из десяти.
    """
    choices = [
        ("Новая заявка", MENU_NEW),
        ("Последние заявки", MENU_LAST),
        ("Часто заказываю", MENU_FREQUENT),
        ("Мои активные", MENU_ACTIVE),
        ("Спросить ORDER AI", MENU_AI),
    ]
    return Reply(f"{employee.full_name}, что делаем?", choices=choices)


def last_requests(session: Session, employee: Employee) -> Reply:
    """Последние заявки сотрудника — свои, а не чужие."""
    rows = list(
        session.scalars(
            select(ExpenseRequest)
            .where(ExpenseRequest.employee_id == employee.id)
            .order_by(ExpenseRequest.created_at.desc())
            .limit(LIST_LIMIT)
        )
    )
    if not rows:
        return Reply("Заявок пока нет. Первую можно подать командой /new.")
    return Reply(
        "<b>Ваши последние заявки</b>\n\n" + "\n".join(_request_line(r) for r in rows),
        button=("Открыть панель", panel_url("/requests")),
    )


def active_requests(session: Session, employee: Employee) -> Reply:
    """Заявки, которые ещё в работе: по ним чего-то ждут."""
    rows = list(
        session.scalars(
            select(ExpenseRequest)
            .where(
                ExpenseRequest.employee_id == employee.id,
                ExpenseRequest.status.in_(IN_WORK),
            )
            .order_by(ExpenseRequest.created_at.desc())
            .limit(LIST_LIMIT)
        )
    )
    if not rows:
        return Reply("В работе ничего нет — всё закрыто.")
    return Reply(
        "<b>В работе</b>\n\n" + "\n".join(_request_line(r, with_stage=True) for r in rows),
        button=("Открыть панель", panel_url("/requests")),
    )


def frequent_materials(session: Session, employee: Employee) -> Reply:
    """Что человек заказывает чаще всего — кнопками.

    Нажатие начинает заявку с этой позиции: повтор прошлой заявки должен
    стоить одно движение, иначе им не пользуются.
    """
    items = ai_memory.mine(session, employee.id, limit=FREQUENT_LIMIT)
    if not items:
        items = ai_memory.frequent(session, limit=FREQUENT_LIMIT)
    if not items:
        return Reply("Пока не из чего выбирать: заявок ещё не было. /new — первая.")

    _save(
        session,
        employee,
        step=STEP_PICK,
        data={"lines": [], "history": [], "materials": [i.title for i in items]},
    )
    return Reply(
        "Что нужно? Выберите или напишите словами.",
        choices=[
            (f"{item.title}" + (f" · {item.unit}" if item.unit else ""), f"{PICK_MATERIAL}{i}")
            for i, item in enumerate(items)
        ],
    )


def pick_material(session: Session, employee: Employee, index: int) -> Reply:
    """Выбрали материал из ленты частых — дальше спрашиваем объект."""
    state = _load(session, employee)
    if state is None or state.step != STEP_PICK:
        return LOST

    materials = list(state.data.get("materials") or [])
    if index >= len(materials):
        return Reply("Этот вариант уже не подходит. Начните заново: /new.")

    data = dict(state.data)
    data["lines"] = [{"title": materials[index], "quantity": 1, "unit": None}]
    data.pop("materials", None)
    _save(session, employee, step=STEP_PROJECT, data=data)

    projects = _active_projects(session)
    if not projects:
        return NO_PROJECTS
    return Reply(
        f"<b>{materials[index]}</b>. На какой объект?",
        choices=[(p.name, f"{PICK_PROJECT}{p.id}") for p in projects],
    )


def templates_of(session: Session, employee: Employee) -> Reply:
    """Шаблоны сотрудника кнопками."""
    rows = templates_svc.list_for(session, employee)
    if not rows:
        return Reply(
            "Шаблонов нет. Их сохраняют в панели: подали заявку, которая "
            "повторяется каждую неделю, — нажали «Сохранить шаблоном»."
        )
    return Reply(
        "Какой шаблон?",
        choices=[(t.name, f"{PICK_TEMPLATE}{t.id}") for t in rows[:FREQUENT_LIMIT]],
    )


def pick_template(session: Session, employee: Employee, template_id: int) -> Reply:
    """Шаблон подставлен — показываем карточку, но не подаём заявку."""
    try:
        template, warning = templates_svc.apply(session, employee, template_id)
    except NotFoundError:
        return Reply("Такого шаблона нет. Посмотреть свои: /templates.")

    lines = templates_svc.lines_of(template)
    data = {
        "lines": lines,
        "history": [],
        "project_id": template.project_id,
        "project_name": None,
    }
    if template.project_id is not None:
        project = session.get(Project, template.project_id)
        data["project_name"] = project.name if project else None
        _save(session, employee, step=STEP_CONFIRM, data=data)
        return _card(data, note=f"Шаблон «{template.name}».")

    _save(session, employee, step=STEP_PROJECT, data=data)
    projects = _active_projects(session)
    if not projects:
        return NO_PROJECTS
    head = f"Шаблон «{template.name}»."
    if warning:
        head += f" {warning}"
    return Reply(
        f"{head} На какой объект?",
        choices=[(p.name, f"{PICK_PROJECT}{p.id}") for p in projects],
    )


def repeat_last(session: Session, employee: Employee, text: str = "") -> Reply:
    """«Как в прошлый раз»: показываем найденное, но ничего не создаём."""
    found = ai_memory.last_like(
        session,
        employee_id=employee.id,
        text=text,
        visible_employee_id=ai_privacy.visible_employee_id(employee),
    )
    if not found:
        return Reply("Похожей заявки не нашёл. Расскажите, что нужно: /new.")

    _save(
        session,
        employee,
        step=STEP_PICK,
        data={
            "lines": [],
            "history": [],
            "repeats": [
                {
                    "number": item.number,
                    "project_id": item.project_id,
                    "project_name": item.project,
                    "lines": item.lines,
                }
                for item in found
            ],
        },
    )
    first = found[0]
    return Reply(
        "<b>Нашёл предыдущий вариант</b>\n\n"
        f"Заявка {first.number}, {_days_ago(first.days_ago)}\n"
        f"Объект: {first.project}\n"
        f"{_lines_text(first.lines)}\n\n"
        "Заявку не подаю: проверьте и решите сами.",
        choices=[
            ("Использовать", f"{PICK_REPEAT}0"),
            *(
                [("Другой вариант", f"{PICK_REPEAT}1")]
                if len(found) > 1
                else []
            ),
            ("Отмена", CONFIRM_CANCEL),
        ],
    )


def pick_repeat(session: Session, employee: Employee, index: int) -> Reply:
    """Взяли один из найденных вариантов — показываем карточку."""
    state = _load(session, employee)
    if state is None or state.step != STEP_PICK:
        return LOST

    options = list(state.data.get("repeats") or [])
    if index >= len(options):
        return Reply("Вариантов больше нет. Расскажите, что нужно: /new.")

    option = options[index]
    data = {
        "lines": option["lines"],
        "history": [],
        "project_id": option.get("project_id"),
        "project_name": option.get("project_name"),
    }
    _save(session, employee, step=STEP_CONFIRM, data=data)
    note = f"Как в заявке {option['number']}."
    if index + 1 < len(options):
        note += " Не то — «Изменить» или /new."
    return _card(data, note=note)


def _active_projects(session: Session) -> list[Project]:
    return list(
        session.scalars(
            select(Project)
            .where(Project.active.is_(True))
            .order_by(Project.name)
            .limit(PROJECT_LIMIT)
        )
    )


def _request_line(request, *, with_stage: bool = False) -> str:
    stage = f" · {awaiting_label(request)}" if with_stage else ""
    return f"• {request.number} — {title_of(request)}{stage}"


def _days_ago(days: int) -> str:
    if days == 0:
        return "сегодня"
    if days == 1:
        return "вчера"
    return f"{days} {plural(days, 'день', 'дня', 'дней')} назад"


#: Как звучит просьба повторить прошлую заявку. Ловим до модели: ответ
#: один и тот же, а запрос к Claude стоит денег и секунд.
REPEAT_MARKERS = (
    "как в прошлый раз", "как в прошлый", "повтори", "повторить",
    "как всегда", "как обычно", "опять", "снова", "то же самое",
    "как вчера", "такой же", "такую же", "как на прошлой",
)


def looks_like_repeat(text: str) -> bool:
    """Просят ли повторить прошлую заявку."""
    low = " ".join((text or "").lower().split())
    return any(marker in low for marker in REPEAT_MARKERS)
