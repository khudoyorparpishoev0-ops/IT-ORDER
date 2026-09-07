"""Схема базы. Менять только через миграции Alembic, create_all в рантайме запрещён."""

from __future__ import annotations

import enum
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Sequence,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAt, Money, Name, ShortStr, Timestamp


class RequestStatus(str, enum.Enum):
    """Статусы заявки. Совпадают с макетом и фронтендом."""

    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    REJECTED = "rejected"


class EmployeeRole(str, enum.Enum):
    """Роль в согласовании.

    EMPLOYEE подаёт заявки и видит только свои. MANAGER согласует чужие,
    FINANCE проводит выплаты, ADMIN ведёт справочники и может всё.
    Права проверяются в app/core/permissions.py.
    """

    EMPLOYEE = "employee"
    MANAGER = "manager"
    FINANCE = "finance"
    ADMIN = "admin"


class PaymentMethod(str, enum.Enum):
    CARD = "card"
    CASH = "cash"


class EventKind(str, enum.Enum):
    """Что произошло с заявкой. Из этого строится «История изменений»."""

    CREATED = "created"
    SUBMITTED = "submitted"
    COMMENTED = "commented"
    VIEWED = "viewed"
    APPROVED = "approved"
    AUTO_APPROVED = "auto_approved"
    REJECTED = "rejected"
    PAID = "paid"


#: Счётчик номеров заявок. Последовательность, а не max(number): она не
#: откатывается вместе с транзакцией, поэтому удалённый или отменённый
#: черновик уже не вернёт свой номер в оборот. Пропуски в нумерации
#: допустимы, повторы — нет.
REQUEST_NUMBER_SEQ = Sequence("request_number_seq", start=1, metadata=Base.metadata)


class Project(Base):
    """Объект, на который списывается расход: «Вилла Колхозная», «Рекова 132»."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[Name] = mapped_column(unique=True)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[CreatedAt]

    requests: Mapped[list[ExpenseRequest]] = relationship(back_populates="project")


class Employee(Base):
    """Сотрудник. Увольнение — active=false, запись не удаляется."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[Name]
    position: Mapped[Name] = mapped_column(default="")
    email: Mapped[str | None] = mapped_column(String(200), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    role: Mapped[EmployeeRole] = mapped_column(
        Enum(EmployeeRole, name="employee_role", native_enum=False, length=16),
        default=EmployeeRole.EMPLOYEE,
        nullable=False,
    )
    #: Месячный лимит расходов в сомони. NULL — лимит не задан.
    monthly_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    active: Mapped[bool] = mapped_column(default=True, nullable=False)

    #: Хэш пароля (Argon2id). NULL — сотрудник заведён, но входить не может:
    #: так заводятся те, кто только фигурирует в заявках.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    last_login_at: Mapped[Timestamp | None]

    #: Секрет TOTP, зашифрованный ключом из SECRET_KEY. Заполнен, но
    #: totp_enabled=false — настройка начата и не подтверждена кодом.
    totp_secret: Mapped[str | None] = mapped_column(String(255))
    totp_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    totp_confirmed_at: Mapped[Timestamp | None]
    #: Номер последнего использованного временного шага: не даёт применить
    #: подсмотренный код повторно в пределах его 30-секундного окна.
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)

    #: Защита от перебора. Шестизначный код TOTP без неё подбирается за часы.
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Timestamp | None]

    #: Письмо о новой заявке на согласование. Приходит только тем, кто
    #: вправе принимать решения.
    notify_new_requests: Mapped[bool] = mapped_column(default=True, nullable=False)
    #: Напоминание о заявках, залежавшихся дольше трёх дней.
    notify_stale_requests: Mapped[bool] = mapped_column(default=True, nullable=False)
    #: Еженедельная сводка по бюджету.
    notify_weekly_budget: Mapped[bool] = mapped_column(default=False, nullable=False)

    created_at: Mapped[CreatedAt]

    requests: Mapped[list[ExpenseRequest]] = relationship(back_populates="employee")
    recovery_codes: Mapped[list[RecoveryCode]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )

    @property
    def can_sign_in(self) -> bool:
        """Войти может активный сотрудник с почтой и заданным паролем."""
        return bool(self.active and self.email and self.password_hash)

    __table_args__ = (
        CheckConstraint(
            "monthly_limit IS NULL OR monthly_limit >= 0",
            name="ck_employees_limit_non_negative",
        ),
    )


class RecoveryCode(Base):
    """Одноразовый код восстановления доступа при потере телефона.

    Хранится хэшем: дамп базы не должен давать возможность войти.
    Использованный код не удаляется, а помечается — по журналу видно,
    что второй фактор обходили кодом восстановления.
    """

    __tablename__ = "recovery_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    used_at: Mapped[Timestamp | None]
    created_at: Mapped[CreatedAt]

    employee: Mapped[Employee] = relationship(back_populates="recovery_codes")

    __table_args__ = (
        Index("ix_recovery_employee", "employee_id"),
        UniqueConstraint("employee_id", "code_hash", name="uq_recovery_employee_code"),
    )


class ExpenseRequest(Base):
    """Заявка на возмещение расходов.

    Сумма (`amount`) — денормализованный итог строк. Пересчитывается сервисом
    при каждом изменении состава: так список и отчёты не тянут строки заявок.
    """

    __tablename__ = "expense_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: Человекочитаемый номер «РЗ-2419». Уникален, показывается везде.
    number: Mapped[ShortStr] = mapped_column(unique=True)

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )

    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, name="request_status", native_enum=False, length=16),
        default=RequestStatus.DRAFT,
        nullable=False,
    )
    amount: Mapped[Money] = mapped_column(default=Decimal("0.00"), nullable=False)

    created_at: Mapped[CreatedAt]
    submitted_at: Mapped[Timestamp | None]
    decided_at: Mapped[Timestamp | None]
    paid_at: Mapped[Timestamp | None]

    #: Комментарий согласующего. При отклонении обязателен.
    decision_comment: Mapped[str | None] = mapped_column(Text)
    #: Кто принял решение. Заполняется из сессии с фазы 3.
    decided_by: Mapped[str | None] = mapped_column(String(200))

    employee: Mapped[Employee] = relationship(back_populates="requests")
    project: Mapped[Project] = relationship(back_populates="requests")
    lines: Mapped[list[ExpenseLine]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="ExpenseLine.id",
    )
    events: Mapped[list[RequestEvent]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="RequestEvent.created_at",
    )
    payment: Mapped[Payment | None] = relationship(
        back_populates="request", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_requests_amount_non_negative"),
        Index("ix_requests_status_created", "status", "created_at"),
        Index("ix_requests_employee_created", "employee_id", "created_at"),
    )


class ExpenseLine(Base):
    """Строка расхода внутри заявки: описание, количество, цена."""

    __tablename__ = "expense_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("expense_requests.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[Name]
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Money] = mapped_column(nullable=False)
    #: Итог строки хранится, а не считается на лету: цена может измениться
    #: в справочнике, а сумма поданной заявки меняться не должна.
    total: Mapped[Money] = mapped_column(nullable=False)

    request: Mapped[ExpenseRequest] = relationship(back_populates="lines")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_lines_quantity_positive"),
        CheckConstraint("price >= 0", name="ck_lines_price_non_negative"),
        CheckConstraint("total >= 0", name="ck_lines_total_non_negative"),
        Index("ix_lines_request", "request_id"),
    )


class RequestEvent(Base):
    """Запись истории. Неизменяема: только добавляется."""

    __tablename__ = "request_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("expense_requests.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[EventKind] = mapped_column(
        Enum(EventKind, name="event_kind", native_enum=False, length=24), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    #: Кто совершил действие. До фазы 3 — имя сотрудника или «СИСТЕМА».
    actor: Mapped[Name] = mapped_column(default="СИСТЕМА")
    created_at: Mapped[CreatedAt]

    request: Mapped[ExpenseRequest] = relationship(back_populates="events")

    __table_args__ = (Index("ix_events_request_created", "request_id", "created_at"),)


class Payment(Base):
    """Выплата по заявке. Одна заявка — одна выплата."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("expense_requests.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Money] = mapped_column(nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method", native_enum=False, length=8),
        nullable=False,
    )
    #: Номер платёжного документа: ПП-0412, РКО-118.
    document: Mapped[ShortStr]
    paid_at: Mapped[Timestamp] = mapped_column(nullable=False)
    created_at: Mapped[CreatedAt]

    request: Mapped[ExpenseRequest] = relationship(back_populates="payment")

    __table_args__ = (
        UniqueConstraint("request_id", name="uq_payments_request"),
        CheckConstraint("amount >= 0", name="ck_payments_amount_non_negative"),
    )


class MonthlyBudget(Base):
    """Бюджет расходов на календарный месяц."""

    __tablename__ = "monthly_budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Money] = mapped_column(nullable=False)
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_budget_year_month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_budget_month_range"),
        CheckConstraint("amount >= 0", name="ck_budget_amount_non_negative"),
    )


class AuditLog(Base):
    """Журнал: кто, что и когда сделал в системе.

    Строки только добавляются. Правка и удаление записей журнала не
    предусмотрены ни через API, ни через панель: журнал нужен именно тем,
    что его нельзя переписать задним числом.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity: Mapped[ShortStr] = mapped_column(nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[ShortStr] = mapped_column(nullable=False)
    #: Имя действующего сотрудника на момент действия. Хранится текстом:
    #: человека могли переименовать или удалить, а журнал должен читаться.
    username: Mapped[str | None] = mapped_column(String(200))
    #: Связь с карточкой — чтобы фильтровать по человеку, а не по строке.
    #: Запись сотрудника удалили — ссылка обнуляется, имя остаётся.
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    #: Адрес, с которого пришёл запрос. Нужен разбору неудачных входов.
    ip: Mapped[str | None] = mapped_column(String(45))
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        Index("ix_audit_entity", "entity", "entity_id"),
        # Журнал читают с конца и постранично — без индекса по времени
        # сортировка каждый раз перебирала бы всю таблицу.
        Index("ix_audit_created_at", "created_at"),
        Index("ix_audit_employee", "employee_id"),
    )


__all__ = [
    "AuditLog",
    "Base",
    "Employee",
    "EmployeeRole",
    "EventKind",
    "ExpenseLine",
    "ExpenseRequest",
    "MonthlyBudget",
    "Payment",
    "PaymentMethod",
    "Project",
    "RecoveryCode",
    "RequestEvent",
    "REQUEST_NUMBER_SEQ",
    "RequestStatus",
]
