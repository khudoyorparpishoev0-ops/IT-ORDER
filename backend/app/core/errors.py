"""Ошибки бизнес-логики. Слой services их поднимает, слой api переводит в HTTP."""


class DomainError(Exception):
    """Базовая ошибка домена."""


class NotFoundError(DomainError):
    """Записи нет. → 404"""


class ConflictError(DomainError):
    """Действие противоречит текущему состоянию. → 409"""


class ValidationError(DomainError):
    """Данные не проходят проверку правил. → 422"""
