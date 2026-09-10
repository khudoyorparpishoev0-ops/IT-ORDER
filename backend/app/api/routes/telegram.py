"""Бот Telegram: привязка чата и приём сообщений.

Вебхук открыт без входа — его вызывает Telegram, а не человек. Защита в
адресе: секрет выводится из SECRET_KEY, знает его только тот, кому мы сами
сообщили адрес (то есть Telegram). Тело запроса дальше секрета не идёт.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, RequirePermission, bind_audit_actor
from app.config import get_settings
from app.core.audit_context import Actor, set_actor
from app.core.errors import ConflictError, ValidationError
from app.core.permissions import Permission
from app.core.telegram import (
    Message,
    TelegramError,
    answer_callback,
    call,
    send_quietly,
)
from app.schemas.telegram import TelegramLinkOut, TelegramSetupOut, TelegramStatusOut
from app.services import telegram_director as director
from app.services import telegram_flow as flow
from app.services import telegram_link as svc
from app.services.notifications import panel_url

from fastapi import Depends

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telegram", tags=["telegram"])

#: Ответы бота. Держим рядом: это единственное место, где он говорит.
GREETING = (
    "Готово, уведомления подключены.\n\n"
    "Буду писать, что происходит с вашими заявками: согласование, оценка "
    "закупа, решение по сумме и выплата."
)
UNKNOWN_CODE = (
    "Ссылка не подошла: код одноразовый и живёт полчаса.\n\n"
    "Откройте в панели «Параметры» → «Telegram» и нажмите «Подключить» ещё раз."
)
NOT_LINKED = (
    "Этот чат ни к кому не привязан.\n\n"
    "Откройте в панели «Параметры» → «Telegram» и нажмите «Подключить»."
)
HELP = (
    "Что я умею:\n\n"
    "/new — подать заявку прямо отсюда\n"
    "/again — повторить прошлую заявку\n"
    "/templates — мои шаблоны\n"
    "/cancel — прервать начатую заявку\n"
    "/stop — отключить уведомления\n\n"
    "Остальное — в панели."
)
#: Отдельная справка руководителю: у него команд больше.
HELP_DIRECTOR = (
    "\nАналитика:\n"
    "/summary — сводка\n"
    "/attention — требуют внимания\n"
    "/overdue — просроченные\n"
    "/stuck — без движения\n"
    "/morning и /evening — сводки за период\n"
    "/ask вопрос — спросить ORDER AI"
)


@router.get(
    "/status",
    response_model=TelegramStatusOut,
    dependencies=[Depends(bind_audit_actor)],
)
def status_(user: CurrentUser):
    settings = get_settings()
    return TelegramStatusOut(
        configured=settings.telegram_enabled and bool(settings.telegram_bot_username),
        linked=user.telegram_chat_id is not None,
        username=user.telegram_username,
        bot_username=settings.telegram_bot_username or None,
    )


@router.post(
    "/link", response_model=TelegramLinkOut, dependencies=[Depends(bind_audit_actor)]
)
def link(session: DbSession, user: CurrentUser):
    """Выдаёт одноразовую ссылку на бота."""
    data = svc.start_link(session, user)
    return TelegramLinkOut(url=data["url"], expires_in_minutes=int(data["expires_in_minutes"]))


@router.post(
    "/unlink",
    response_model=TelegramStatusOut,
    dependencies=[Depends(bind_audit_actor)],
)
def unlink(session: DbSession, user: CurrentUser):
    svc.unlink(session, user, actor=user.full_name)
    settings = get_settings()
    return TelegramStatusOut(
        configured=settings.telegram_enabled and bool(settings.telegram_bot_username),
        linked=False,
        username=None,
        bot_username=settings.telegram_bot_username or None,
    )


@router.post(
    "/setup",
    response_model=TelegramSetupOut,
    dependencies=[
        Depends(bind_audit_actor),
        Depends(RequirePermission(Permission.MANAGE_REFERENCE)),
    ],
)
def setup_webhook():
    """Говорит Telegram, куда слать обновления.

    Делается кнопкой в панели, а не руками через curl: адрес содержит
    секрет из SECRET_KEY, и при смене ключа вебхук надо переустановить —
    администратору проще нажать кнопку, чем собирать адрес самому.
    """
    settings = get_settings()
    if not settings.telegram_enabled:
        raise ValidationError("Telegram не настроен: задайте TELEGRAM_BOT_TOKEN")
    if not settings.public_base_url:
        raise ValidationError(
            "Не задан PUBLIC_BASE_URL — Telegram некуда слать обновления"
        )

    url = f"{settings.public_base_url.rstrip('/')}/api/telegram/webhook/{settings.telegram_webhook_secret}"
    try:
        call(
            "setWebhook",
            # Нажатия кнопок приходят отдельным типом обновления: без него
            # карточка подтверждения заявки была бы нажимаемой, но немой.
            {"url": url, "allowed_updates": ["message", "callback_query"]},
        )
    except TelegramError as exc:
        raise ValidationError(str(exc)) from exc

    log.info("Вебхук Telegram установлен")
    return TelegramSetupOut(
        webhook_url=url, bot_username=settings.telegram_bot_username or None
    )


@router.post("/webhook/{secret}", include_in_schema=False)
async def webhook(secret: str, session: DbSession, request: Request):
    """Приём обновлений от Telegram.

    Отвечаем 200 почти всегда: на ошибку Telegram повторяет доставку, а
    повторять разбор чужого сообщения незачем.
    """
    settings = get_settings()
    if not settings.telegram_enabled or secret != settings.telegram_webhook_secret:
        # Тем, кто угадывает адрес, ничего не рассказываем.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    update = await request.json()

    # Нажатие кнопки под сообщением: карточка подтверждения заявки,
    # выбор объекта, готовый вариант ответа.
    press = update.get("callback_query")
    if press:
        chat_id = ((press.get("message") or {}).get("chat") or {}).get("id")
        code = (press.get("data") or "").strip()
        if press.get("id"):
            answer_callback(str(press["id"]))
        if chat_id:
            _handle_press(session, int(chat_id), code)
        return {"ok": True}

    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if not chat_id:
        return {"ok": True}

    if text.startswith("/start"):
        code = text[len("/start") :].strip()
        try:
            employee = svc.complete_link(
                session,
                code,
                chat_id=int(chat_id),
                username=(message.get("from") or {}).get("username"),
            )
        except ConflictError as exc:
            _reply(chat_id, str(exc))
            return {"ok": True}

        if employee is None:
            _reply(chat_id, UNKNOWN_CODE)
        else:
            session.commit()
            _reply(chat_id, f"{employee.full_name}, {GREETING}")
            # Сразу показываем, что можно сделать: команды с телефона на
            # стройке никто не набирает, а кнопки нажимают.
            _send(chat_id, flow.menu(employee))
        return {"ok": True}

    if text.startswith("/stop"):
        employee = svc.by_chat(session, int(chat_id))
        if employee is not None:
            svc.unlink(session, employee)
            session.commit()
            _reply(chat_id, "Уведомления отключены. Вернуть их можно в панели.")
        else:
            _reply(chat_id, NOT_LINKED)
        return {"ok": True}

    employee = svc.by_chat(session, int(chat_id))
    if employee is None:
        _reply(chat_id, NOT_LINKED)
        return {"ok": True}
    if not employee.active:
        _reply(chat_id, "Учётная запись отключена. Обратитесь к администратору.")
        return {"ok": True}
    _bind(employee)

    if text.startswith("/new"):
        # Сначала коммит, потом сообщение: иначе человек прочтёт про шаг,
        # которого в базе не осталось.
        reply = flow.start(session, employee)
        session.commit()
        _send(chat_id, reply)
        return {"ok": True}

    if text.startswith("/cancel"):
        reply = flow.cancel(session, employee)
        session.commit()
        _send(chat_id, reply)
        return {"ok": True}

    if text.startswith("/again"):
        reply = flow.repeat_last(session, employee, text[len("/again") :].strip())
        session.commit()
        _send(chat_id, reply)
        return {"ok": True}

    if text.startswith("/templates"):
        reply = flow.templates_of(session, employee)
        session.commit()
        _send(chat_id, reply)
        return {"ok": True}

    if text.startswith("/help") or text.startswith("/menu"):
        _reply(chat_id, HELP + (HELP_DIRECTOR if director.available(employee) else ""))
        _send(chat_id, flow.menu(employee))
        return {"ok": True}

    # Директорские команды. Право проверяет сам сервис — здесь только
    # разбор текста: правило доступа должно быть в одном месте.
    dir_reply = _director_command(session, employee, text)
    if dir_reply is not None:
        session.commit()
        _send(chat_id, dir_reply)
        return {"ok": True}

    # Обычный текст — это ответ боту, если разговор идёт. Иначе человек
    # написал в пустоту, и подсказать ему нужно то, что он может сделать.
    if text and not text.startswith("/") and flow.in_dialogue(session, employee):
        reply = flow.handle_text(session, employee, text)
        session.commit()
        _send(chat_id, reply)
        return {"ok": True}

    if text and not text.startswith("/"):
        # Разговор не идёт. «Как в прошлый раз», «повтори прошлую
        # заявку», «мне опять этот кабель» — это просьба найти прошлое, а
        # не начать разговор с нуля.
        if flow.is_for_someone_else(text):
            _reply(chat_id, flow.FOREIGN_REQUEST)
            return {"ok": True}
        if flow.looks_like_repeat(text):
            reply = flow.repeat_last(session, employee, text)
            session.commit()
            _send(chat_id, reply)
            return {"ok": True}

    _send(chat_id, flow.menu(employee))
    return {"ok": True}


def _handle_press(session: Session, chat_id: int, code: str) -> None:
    """Разбор нажатой кнопки. Право проверяется у каждого шага: разговор
    мог начаться вчера, а роль с тех пор понизили."""
    employee = svc.by_chat(session, chat_id)
    if employee is None or not employee.active:
        _reply(chat_id, NOT_LINKED)
        return
    _bind(employee)

    if code.startswith(flow.PICK_PROJECT):
        reply = flow.pick_project(session, employee, _number(code, flow.PICK_PROJECT))
    elif code.startswith(flow.PICK_OPTION):
        reply = flow.pick_option(session, employee, _number(code, flow.PICK_OPTION))
    elif code.startswith(flow.PICK_MATERIAL):
        reply = flow.pick_material(session, employee, _number(code, flow.PICK_MATERIAL))
    elif code.startswith(flow.PICK_TEMPLATE):
        reply = flow.pick_template(session, employee, _number(code, flow.PICK_TEMPLATE))
    elif code.startswith(flow.PICK_REPEAT):
        reply = flow.pick_repeat(session, employee, _number(code, flow.PICK_REPEAT))
    elif code == flow.MENU_NEW:
        reply = flow.start(session, employee)
    elif code == flow.MENU_LAST:
        reply = flow.last_requests(session, employee)
    elif code == flow.MENU_ACTIVE:
        reply = flow.active_requests(session, employee)
    elif code == flow.MENU_FREQUENT:
        reply = flow.frequent_materials(session, employee)
    elif code == flow.MENU_AI:
        reply = flow.start(session, employee)
    elif code.startswith(director.DIR_PAGE):
        reply = _director_page(session, employee, code)
    elif code.startswith(director.DIR_RATE):
        reply = _director_rate(session, employee, code)
    elif code == director.DIR_OVERVIEW:
        reply = director.overview(session, employee)
    elif code == director.DIR_ATTENTION:
        reply = director.attention_page(session, employee)
    elif code == director.DIR_STUCK:
        reply = director.stuck_page(session, employee)
    elif code == director.DIR_OVERDUE:
        reply = director.overdue_page(session, employee)
    elif code == director.DIR_PROJECTS:
        reply = director.projects(session, employee)
    elif code == director.DIR_ASK:
        reply = director.ask_prompt()
    elif code == director.DIR_MORNING:
        reply = director.digest_reply(session, employee, "morning")
    elif code == director.DIR_EVENING:
        reply = director.digest_reply(session, employee, "evening")
    elif code == flow.CONFIRM_SEND:
        reply = flow.confirm(session, employee)
    elif code == flow.CONFIRM_EDIT:
        reply = flow.edit(session, employee)
    elif code == flow.CONFIRM_CANCEL:
        reply = flow.cancel(session, employee)
    else:
        reply = flow.LOST

    session.commit()
    _send(chat_id, reply)


def _bind(employee) -> None:
    """Кто действует в этом обновлении от Telegram.

    Вебхук открыт без входа, поэтому зависимости `bind_audit_actor` на
    нём нет — а журнал действий и журнал обращений к AI берут человека
    именно из контекста. Без этой строки запись из бота осталась бы
    безымянной, и оценить свой же ответ человек не смог бы.

    Ставим здесь, а не глубже: обработчик асинхронный, и контекст
    доживает до всего, что он зовёт.
    """
    set_actor(Actor(id=employee.id, name=employee.full_name))


def _director_command(session: Session, employee, text: str):
    """Директорская команда или None, если это не она."""
    if text.startswith("/summary") or text.lower().startswith("сводка"):
        return director.overview(session, employee)
    if text.startswith("/attention"):
        return director.attention_page(session, employee)
    if text.startswith("/overdue"):
        return director.overdue_page(session, employee)
    if text.startswith("/stuck"):
        return director.stuck_page(session, employee)
    if text.startswith("/projects"):
        return director.projects(session, employee)
    if text.startswith("/morning"):
        return director.digest_reply(session, employee, "morning")
    if text.startswith("/evening"):
        return director.digest_reply(session, employee, "evening")
    if text.startswith("/ask"):
        question = text[len("/ask") :].strip()
        if not question:
            return director.ask_prompt()
        return director.ask(session, employee, question)
    return None


def _director_page(session: Session, employee, code: str):
    """Перелистывание списка: `dir:page:att:2`."""
    tail = code[len(director.DIR_PAGE) :]
    kind, _, number = tail.partition(":")
    try:
        page = int(number)
    except ValueError:
        page = 0
    if kind == "att":
        return director.attention_page(session, employee, page)
    if kind == "over":
        return director.overdue_page(session, employee, page)
    if kind == "stuck":
        return director.stuck_page(session, employee, page)
    return director.overview(session, employee)


def _director_rate(session: Session, employee, code: str):
    """Оценка ответа помощника: `dir:rate:1:42`."""
    tail = code[len(director.DIR_RATE) :]
    useful, _, number = tail.partition(":")
    try:
        interaction_id = int(number)
    except ValueError:
        return flow.LOST
    return director.rate(session, employee, useful == "1", interaction_id)


def _number(code: str, prefix: str) -> int:
    try:
        return int(code[len(prefix) :])
    except ValueError:
        return 0


def _send(chat_id: int, reply: flow.Reply) -> None:
    send_quietly(
        Message(
            chat_id=int(chat_id),
            text=reply.text,
            choices=reply.choices,
            button=reply.button,
        )
    )


def _reply(chat_id: int, text: str, *, with_button: bool = False) -> None:
    send_quietly(
        Message(
            chat_id=int(chat_id),
            text=text,
            button=("Открыть панель", panel_url("/")) if with_button else None,
        )
    )
