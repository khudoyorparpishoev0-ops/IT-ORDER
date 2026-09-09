"""Понятные названия для журнала.

Коды действий в базе короткие и латиницей — по ним удобно фильтровать и
искать. Человеку в панели и в выгрузке показываем эти подписи. Такой же
словарь есть во фронтенде (`src/data/audit.ts`) — добавили действие здесь,
добавьте и там, иначе в интерфейсе останется голый код.
"""

from __future__ import annotations

ENTITY_LABEL: dict[str, str] = {
    "employee": "Сотрудник",
    "project": "Объект",
    "request": "Заявка",
    "job": "Фоновая задача",
    "budget": "Бюджет месяца",
    "template": "Шаблон заявки",
    "analytics": "AI-аналитика",
}

ACTION_LABEL: dict[str, str] = {
    # Доступ
    "login": "Вход в систему",
    "logout": "Выход",
    "login_failed": "Неудачный вход",
    "login_locked": "Вход заблокирован",
    "password_changed": "Сменил себе пароль",
    "set_password": "Пароль выдан администратором",
    "password_reset_requested": "Запрошено восстановление пароля",
    "password_reset_applied": "Пароль восстановлен по ссылке",
    "totp_enabled": "Второй фактор включён",
    "totp_disabled": "Второй фактор выключен",
    "totp_reset_by_admin": "Второй фактор сброшен администратором",
    "recovery_code_used": "Вход по коду восстановления",
    "recovery_codes_reissued": "Коды восстановления перевыпущены",
    "telegram_linked": "Telegram подключён",
    "telegram_unlinked": "Telegram отключён",
    "push_subscribed": "Уведомления на телефон включены",
    "push_unsubscribed": "Уведомления на телефон отключены",
    "bootstrap_admin": "Создан стартовый администратор",
    # Шаблоны заявок
    "template_created": "Шаблон создан",
    "template_updated": "Шаблон изменён",
    "template_deleted": "Шаблон удалён",
    # AI
    "ai_question": "Вопрос AI-аналитику",
    # Справочники
    "create": "Создание",
    "update": "Изменение",
    "delete": "Удаление",
    # Заявки
    "submit": "Отправлена на согласование",
    "sourcing": "Покупка согласована, передана в закуп",
    "priced": "Оценена закупом",
    "fulfilled": "Закрыта складом",
    "approve": "Одобрена",
    "reject": "Отклонена",
    "auto_approve": "Одобрена автоматически",
    "pay": "Выплата проведена",
    # Фоновые задачи
    "job_run": "Задача запущена вручную",
}


def entity_label(entity: str) -> str:
    return ENTITY_LABEL.get(entity, entity)


def action_label(action: str) -> str:
    return ACTION_LABEL.get(action, action)
