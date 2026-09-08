"""Бот Telegram: привязка чата и приём сообщений.

Вебхук открыт без входа — его вызывает Telegram, а не человек. Защита в
адресе: секрет выводится из SECRET_KEY, знает его только тот, кому мы сами
сообщили адрес (то есть Telegram). Тело запроса дальше секрета не идёт.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import CurrentUser, DbSession, RequirePermission, bind_audit_actor
from app.config import get_settings
from app.core.errors import ConflictError, ValidationError
from app.core.permissions import Permission
from app.core.telegram import Message, TelegramError, call, send_quietly
from app.schemas.telegram import TelegramLinkOut, TelegramSetupOut, TelegramStatusOut
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
        call("setWebhook", {"url": url, "allowed_updates": ["message"]})
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
            _reply(chat_id, f"{employee.full_name}, {GREETING}", with_button=True)
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
    _reply(
        chat_id,
        "Я только присылаю уведомления о заявках.\n\n"
        "Всё остальное — в панели."
        if employee is not None
        else NOT_LINKED,
        with_button=employee is not None,
    )
    return {"ok": True}


def _reply(chat_id: int, text: str, *, with_button: bool = False) -> None:
    send_quietly(
        Message(
            chat_id=int(chat_id),
            text=text,
            button=("Открыть панель", panel_url("/")) if with_button else None,
        )
    )
