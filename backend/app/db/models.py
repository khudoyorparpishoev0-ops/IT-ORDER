"""Схема базы. Менять только через миграции Alembic, create_all в рантайме запрещён."""

from __future__ import annotations

import enum
from datetime import time
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
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAt, Money, Name, ShortStr, Timestamp


class RequestStatus(str, enum.Enum):
    """Статусы заявки. Порядок соответствует пути закупки.

    Сотрудник описывает потребность без цен: цены знает отдел закупа.
    Руководитель решает дважды — сначала нужна ли покупка вообще, потом
    согласна ли компания с суммой.
    """

    DRAFT = "draft"
    #: Потребность на согласовании у руководителя.
    PENDING = "pending"
    #: У отдела закупа: проверка склада и цены.
    SOURCING = "sourcing"
    #: Цены проставлены, сумма ждёт решения руководителя.
    PRICED = "priced"
    #: Сумма утверждена, ждёт оплаты.
    APPROVED = "approved"
    PAID = "paid"
    #: Всё нашлось на складе — выдано, денег не потребовалось.
    FULFILLED = "fulfilled"
    REJECTED = "rejected"


class RequestCategory(str, enum.Enum):
    """Бизнес-категория заявки. Не справочник материалов — их одиннадцать
    на всю компанию, и меняются они раз в годы.

    Нужна аналитике руководителя: «на транспорт за месяц ушло столько» —
    вопрос, на который по названиям материалов не ответить. Материалы
    по-прежнему никто не ведёт справочником, а категорий ровно столько,
    сколько влезает в один выпадающий список.

    Значение может отсутствовать: старые заявки её не знают, и заставлять
    людей проставлять её задним числом никто не станет. NULL честно
    значит «не указана», а не «Другое».
    """

    MATERIALS = "MATERIALS"
    EQUIPMENT = "EQUIPMENT"
    TRANSPORT = "TRANSPORT"
    FUEL = "FUEL"
    MEALS = "MEALS"
    LODGING = "LODGING"
    TRIP = "TRIP"
    DELIVERY = "DELIVERY"
    SERVICES = "SERVICES"
    HOUSEHOLD = "HOUSEHOLD"
    OTHER = "OTHER"


class EmployeeRole(str, enum.Enum):
    """Роль в согласовании.

    EMPLOYEE подаёт заявки и видит только свои. MANAGER согласует чужие —
    сначала потребность, потом сумму. PROCUREMENT проверяет склад и ставит
    цены. FINANCE проводит выплаты, ADMIN ведёт справочники и может всё.
    Права проверяются в app/core/permissions.py.
    """

    EMPLOYEE = "employee"
    MANAGER = "manager"
    #: Отдел закупа: проверяет склад и проставляет цены.
    PROCUREMENT = "procurement"
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
    #: Потребность одобрена, заявка ушла в закуп.
    SOURCING = "sourcing"
    #: Закуп проверил склад и проставил цены.
    PRICED = "priced"
    #: Строка закрыта складом — покупать не нужно.
    FULFILLED = "fulfilled"
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

    #: Чат в Telegram, куда слать уведомления. NULL — не привязан.
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    #: @имя из Telegram — чтобы человек узнал свою привязку в панели.
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    telegram_linked_at: Mapped[Timestamp | None]
    #: Одноразовый код привязки и срок его жизни. Код уходит в ссылку
    #: https://t.me/бот?start=<код>, по нему бот и узнаёт, кто написал.
    telegram_link_code: Mapped[str | None] = mapped_column(String(32))
    telegram_link_expires_at: Mapped[Timestamp | None]

    #: Письмо о новой заявке на согласование. Приходит только тем, кто
    #: вправе принимать решения.
    notify_new_requests: Mapped[bool] = mapped_column(default=True, nullable=False)
    #: Напоминание о заявках, залежавшихся дольше трёх дней.
    notify_stale_requests: Mapped[bool] = mapped_column(default=True, nullable=False)
    #: Еженедельная сводка по бюджету.
    notify_weekly_budget: Mapped[bool] = mapped_column(default=False, nullable=False)

    # --- ORDER Intelligence: автоматические сводки руководителю ---
    #: Главный выключатель. Отдельного «доставлять в Telegram» нет: канал
    #: один, и его выключатель уже есть — отвязка чата. Второй флаг,
    #: который не может отличаться от первого, однажды с ним разойдётся.
    intelligence_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    digest_morning_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    digest_evening_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    #: Во сколько по местному времени человека. Не общий час на всех:
    #: у одного день начинается в семь, у другого в десять.
    digest_morning_time: Mapped[time] = mapped_column(
        Time, default=time(9, 0), nullable=False
    )
    digest_evening_time: Mapped[time] = mapped_column(
        Time, default=time(18, 0), nullable=False
    )
    critical_alerts_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    #: Слать сводку, когда разбирать нечего. По умолчанию нет: сводка «всё
    #: спокойно» каждый вечер учит не открывать сводки вообще.
    digest_when_no_changes: Mapped[bool] = mapped_column(default=False, nullable=False)
    #: Часовой пояс человека. Пусто — корпоративный (`APP_TIMEZONE`).
    timezone: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[CreatedAt]

    requests: Mapped[list[ExpenseRequest]] = relationship(back_populates="employee")
    recovery_codes: Mapped[list[RecoveryCode]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    push_subscriptions: Mapped[list[PushSubscription]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )

    @property
    def can_sign_in(self) -> bool:
        """Войти может активный сотрудник с почтой и заданным паролем."""
        return bool(self.active and self.email and self.password_hash)

    __table_args__ = (
        # Один чат — один сотрудник: иначе уведомления двух человек
        # сходились бы в одну переписку.
        UniqueConstraint("telegram_chat_id", name="uq_employees_telegram_chat"),
        Index("ix_employees_telegram_code", "telegram_link_code"),
    )


class PushSubscription(Base):
    """Подписка браузера на push-уведомления: один телефон (или один
    браузер на компьютере) — одна строка.

    Подписку выдаёт push-служба браузера, у неё нет ни имени, ни срока.
    Умирает она без предупреждения (снятое с экрана приложение,
    переустановка), поэтому сервер удаляет строку, как только служба
    ответит 404/410. Ключи p256dh и auth — шифрование до телефона:
    push-служба видит только факт уведомления, не текст.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(128), nullable=False)
    auth: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Чем подписались — чтобы в журнале было видно «iPhone» или «Chrome».
    user_agent: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[CreatedAt]
    last_used_at: Mapped[Timestamp | None]

    employee: Mapped[Employee] = relationship(back_populates="push_subscriptions")

    def info(self) -> dict:
        """В том виде, какой принимает pywebpush."""
        return {"endpoint": self.endpoint, "keys": {"p256dh": self.p256dh, "auth": self.auth}}

    __table_args__ = (
        # Один endpoint — один человек: переустановка того же браузера
        # под другой учётной записью переводит подписку, а не дублирует.
        UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
        Index("ix_push_subscriptions_employee", "employee_id"),
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
    #: Бизнес-категория: транспорт, топливо, питание. NULL — не указана;
    #: старые заявки её не знают, и это честнее, чем свалить их в «Другое».
    #: Помощник предлагает, человек подтверждает — сама не проставляется.
    category: Mapped[RequestCategory | None] = mapped_column(
        Enum(RequestCategory, name="request_category", native_enum=False, length=16)
    )

    created_at: Mapped[CreatedAt]
    submitted_at: Mapped[Timestamp | None]
    #: Когда заявку передали в закуп. Нужно, чтобы честно показывать,
    #: сколько она у них лежит.
    sourcing_started_at: Mapped[Timestamp | None]
    #: Когда закуп вернул заявку с ценами или закрыл её складом.
    sourced_at: Mapped[Timestamp | None]
    #: Итоговое решение по сумме.
    decided_at: Mapped[Timestamp | None]
    paid_at: Mapped[Timestamp | None]

    #: Комментарий согласующего. При отклонении обязателен.
    decision_comment: Mapped[str | None] = mapped_column(Text)
    #: Кто принял решение. Заполняется из сессии с фазы 3.
    decided_by: Mapped[str | None] = mapped_column(String(200))
    #: Кто из отдела закупа оценил заявку.
    sourced_by: Mapped[str | None] = mapped_column(String(200))
    #: Комментарий закупа: почему такие цены, что нашлось на складе.
    sourcing_comment: Mapped[str | None] = mapped_column(Text)

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
        Index("ix_requests_category_created", "category", "created_at"),
    )


class ExpenseLine(Base):
    """Строка расхода внутри заявки: описание, количество, цена."""

    __tablename__ = "expense_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("expense_requests.id", ondelete="CASCADE"), nullable=False
    )
    #: Итоговое название позиции — то, что вошло в заявку. Именно его
    #: видят закуп, бухгалтерия и отчёты.
    title: Mapped[Name]
    #: Что человек набрал своими руками, до всякой правки. Отдельно от
    #: `title`, потому что это разные вещи: приняв поправку помощника
    #: («гофра16» → «Гофра гибкая 16 мм»), человек меняет `title`, и
    #: набранное им исчезает. По `original_text` видно, как люди на самом
    #: деле называют вещи, — без этого нельзя ни проверить помощника, ни
    #: понять, что стоит добавить в подсказки.
    original_text: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    #: Приведённое написание (`services/material_norm.py`): по нему идёт
    #: поиск, подсказки и поиск дублей. Показываем всегда `title`.
    normalized_text: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Единица измерения словами: «шт.», «мешок», «м²». Сотрудник пишет
    #: как привык — справочника единиц у нас нет.
    unit: Mapped[str | None] = mapped_column(String(32))
    #: Цена за единицу. NULL — строку ещё не оценил закуп: сотрудник
    #: описывает потребность, цены он знать не обязан.
    price: Mapped[Money | None] = mapped_column()
    #: Итог строки хранится, а не считается на лету: цена может измениться
    #: в справочнике, а сумма поданной заявки меняться не должна.
    total: Mapped[Money | None] = mapped_column()
    #: Закуп нашёл материал на складе: покупать не нужно, в сумму заявки
    #: строка не входит.
    from_stock: Mapped[bool] = mapped_column(default=False, nullable=False)

    request: Mapped[ExpenseRequest] = relationship(back_populates="lines")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_lines_quantity_positive"),
        CheckConstraint("price IS NULL OR price >= 0", name="ck_lines_price_non_negative"),
        CheckConstraint("total IS NULL OR total >= 0", name="ck_lines_total_non_negative"),
        Index("ix_lines_request", "request_id"),
        Index("ix_lines_normalized", "normalized_text"),
    )


class MaterialAlias(Base):
    """Как сотрудник написал — и как это называют в компании.

    Справочника материалов в ORDER нет намеренно: вести его никто не
    станет, он устареет за месяц. Эта таблица — не справочник: её никто
    не заполняет руками. Строка появляется сама, когда человек нажал
    «Применить» на совете помощника: значит, поправка признана верной
    именно людьми, а не моделью.

    Польза двойная. Следующему сотруднику подсказка приходит мгновенно и
    бесплатно, без похода к модели; а написание в заявках сходится, и
    один материал перестаёт расползаться на пять вариантов в отчётах.
    """

    __tablename__ = "material_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: Приведённое написание, которое ввёл человек. Ключ поиска.
    alias: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    #: Написание, которое показываем: как это называют в компании.
    canonical: Mapped[Name]
    unit: Mapped[str | None] = mapped_column(String(32))
    #: Сколько раз поправку принимали. Чем больше, тем она вернее.
    uses: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[Timestamp | None]


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


class AiFeedback(Base):
    """Оценка ответа помощника человеком: подошло или нет и почему.

    Отдельно от `ai_interactions`, потому что это другая природа данных:
    там факт обращения, здесь мнение человека. Живёт ровно столько,
    сколько живёт само обращение (`ON DELETE CASCADE`): оценка без
    ответа, к которому она относится, не значит ничего.

    Один человек — одна оценка на обращение: передумал и нажал другое —
    заменяем, а не копим.
    """

    __tablename__ = "ai_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interaction_id: Mapped[int] = mapped_column(
        ForeignKey("ai_interactions.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    #: True — «полезно», False — «не подходит».
    useful: Mapped[bool] = mapped_column(nullable=False)
    #: Причина отказа из готового списка (`app/services/ai_feedback.py`).
    reason: Mapped[str | None] = mapped_column(String(64))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        UniqueConstraint("interaction_id", "employee_id", name="uq_ai_feedback_once"),
        Index("ix_ai_feedback_created", "created_at"),
    )


class RequestTemplate(Base):
    """Часто повторяющаяся заявка, сохранённая человеком.

    «Заправка Opel», «Обед сотрудников», «UTP Cat6 на Регар» — это
    заявки, которые подают каждую неделю одними и теми же словами.
    Шаблон превращает их в одно нажатие.

    Шаблон принадлежит человеку, а не компании: у каждого свои
    повторяющиеся дела, а общий список шаблонов пришлось бы кому-то
    вести. Создаётся только руками — помощник может предложить сохранить
    шаблон, но не завести его сам.

    Состав хранится в `payload` как в форме (позиции с количеством и
    единицей): заявка неизменяема после подачи, а шаблон — заготовка,
    и связывать его с конкретной заявкой нельзя, та может быть удалена.
    """

    __tablename__ = "request_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[Name]
    #: Объект по умолчанию. NULL — спрашиваем при применении: «Обед
    #: сотрудников» бывает на любом объекте.
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL")
    )
    #: Позиции: [{"title", "quantity", "unit"}]. Форма шаблона совпадает
    #: с формой заявки, поэтому применение — это подстановка, а не разбор.
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[Timestamp | None]
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[Timestamp | None]

    __table_args__ = (
        UniqueConstraint("employee_id", "name", name="uq_template_name_per_employee"),
        Index("ix_templates_employee", "employee_id"),
    )


class IntelligenceKind(str, enum.Enum):
    """Что именно отправили руководителю."""

    MORNING = "MORNING"
    EVENING = "EVENING"
    CRITICAL = "CRITICAL"


class IntelligenceDelivery(Base):
    """Отправленная сводка или сигнал: и защита от повторов, и история.

    Одна таблица на три роли сразу — и это не экономия, а так и должно
    быть: «уже отправляли» и «когда отправляли» — один и тот же факт.

    `dedup_key` уникален и делает всю работу:

    * у сводки это `morning:<сотрудник>:<местная дата>` — вставка либо
      проходит, либо нет, и два процесса не разошлют одно дважды;
    * у сигнала это `critical:<сотрудник>:<заявка>:<тип>` — одна и та же
      проблема не приходит каждые двадцать минут.

    Повтор важного сигнала не создаёт новую строку, а поднимает
    `sent_count` и `last_sent_at` у существующей: иначе «сколько раз мы
    об этом писали» пришлось бы считать группировкой.

    Устранённая проблема получает `resolved_at`. Отдельного сообщения об
    этом не шлём — человек и так увидит: оно уходит в вечернюю сводку
    строкой «из утренних просрочек устранено N».
    """

    __tablename__ = "intelligence_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[IntelligenceKind] = mapped_column(
        Enum(IntelligenceKind, name="intelligence_kind", native_enum=False, length=16),
        nullable=False,
    )
    #: Ключ, по которому решается «уже отправляли или нет».
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    #: Заявка, о которой сигнал. NULL — сводка, она не про одну заявку.
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("expense_requests.id", ondelete="SET NULL")
    )
    #: Почему заявка попала в сигнал: overdue, stuck, inconsistency.
    reason: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[CreatedAt]
    #: Когда сообщение действительно ушло. NULL — не ушло вовсе.
    delivered_at: Mapped[Timestamp | None]
    last_sent_at: Mapped[Timestamp | None]
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Проблема исчезла из очереди. У сводок не заполняется.
    resolved_at: Mapped[Timestamp | None]

    #: Куда доставляли. Сегодня канал один (telegram), но история должна
    #: отвечать на вопрос «куда ушло», а не «куда ушло бы, если бы
    #: каналов было несколько»: появится второй — старые записи останутся
    #: верными, а не станут неопределёнными задним числом.
    channel: Mapped[str] = mapped_column(String(16), default="telegram", nullable=False)
    ok: Mapped[bool] = mapped_column(default=True, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    #: Сколько заявок вошло в сообщение. По нему видно, была ли сводка
    #: пустой и стоило ли её слать.
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Объясняла ли сводку модель. False — ушёл детерминированный текст.
    ai_used: Mapped[bool] = mapped_column(default=False, nullable=False)

    __table_args__ = (
        Index("ix_intel_employee_kind", "employee_id", "kind"),
        Index("ix_intel_created", "created_at"),
        Index("ix_intel_unresolved", "resolved_at"),
    )


class TelegramSession(Base):
    """Незаконченный разговор с ботом: на каком шаге и что уже набрали.

    Единственное место, где у нас есть состояние диалога. В панели его
    нет намеренно — историю реплик присылает браузер, и сервер ничего не
    помнит. У Telegram браузера нет: между двумя сообщениями разговор
    держать больше негде, поэтому он живёт здесь.

    Один сотрудник — один разговор: `/new` начинает заново и затирает
    прежний. Незаконченные протухают через сутки: заявка, которую начали
    вчера и бросили, сегодня уже про другое.
    """

    __tablename__ = "telegram_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    #: Шаг разговора: PROJECT → NEED → CLARIFY → CONFIRM.
    step: Mapped[ShortStr] = mapped_column(nullable=False)
    #: Что набрали: объект, позиции, реплики. Форма шага своя, поэтому
    #: столбцами это не разложить — да и не нужно: читает эти данные
    #: только сам разговор.
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[Timestamp | None]


class AiKind(str, enum.Enum):
    """Какой помощник отвечал. По этому полю считается польза каждого."""

    #: Проверка написания одного материала в строке заявки.
    MATERIAL = "MATERIAL"
    #: Диалог по заявке: разобрать потребность и собрать позиции.
    REQUEST = "REQUEST"
    #: Вопрос руководителя аналитику.
    ANALYTICS = "ANALYTICS"


class AiSource(str, enum.Enum):
    """Откуда пришло обращение."""

    WEB = "WEB"
    TELEGRAM = "TELEGRAM"


class AiInteraction(Base):
    """Обращение к AI: кто спросил, что ответили, пригодилось ли.

    Это журнал, а не память. Модели эта таблица не показывается никогда:
    память помощника — сами заявки (`expense_requests`, `expense_lines`),
    а здесь мы храним, помогает помощник или мешает. Без такой записи
    вопрос «стоит ли он своих денег» отвечается только на глаз.

    Чего здесь нет и не будет: ключа Anthropic и любых секретов. В
    `question` и `answer` попадает то, что человек и так видел на экране,
    обрезанное по длине — платить за хранение целых диалогов незачем.
    """

    __tablename__ = "ai_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[AiKind] = mapped_column(
        Enum(AiKind, name="ai_kind", native_enum=False, length=16), nullable=False
    )
    source: Mapped[AiSource] = mapped_column(
        Enum(AiSource, name="ai_source", native_enum=False, length=16),
        default=AiSource.WEB,
        nullable=False,
    )
    #: Кто спрашивал. Запись сотрудника удалили — ссылка обнуляется,
    #: имя остаётся: журнал должен читаться и после увольнения.
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    username: Mapped[str | None] = mapped_column(String(200))

    question: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    #: Модель ответила. False — ключа нет, таймаут, отказ Anthropic.
    ok: Mapped[bool] = mapped_column(default=True, nullable=False)
    #: Причина отказа целиком, как её назвал Anthropic. Ключа тут нет.
    error: Mapped[str | None] = mapped_column(Text)
    #: Сколько ждали ответа. По нему видно, растёт ли задержка.
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    #: Человек воспользовался ответом: нажал «Применить». NULL — ответ
    #: такой кнопки не предполагал (вопрос аналитику).
    applied: Mapped[bool | None] = mapped_column()
    #: Какой моделью отвечали. Модель меняют в `.env`, и сравнивать
    #: качество ответов имеет смысл только внутри одной.
    model: Mapped[str | None] = mapped_column(String(64))
    #: Токены на вход и выход, если Anthropic их вернул. По ним считается
    #: стоимость ORDER AI: без них она известна только из счёта.
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        Index("ix_ai_created_at", "created_at"),
        Index("ix_ai_employee", "employee_id"),
        Index("ix_ai_kind_created", "kind", "created_at"),
    )


class JobRun(Base):
    """Запуск фоновой задачи: напоминания, недельная сводка.

    Ключ запуска (`run_key` вида «stale_requests:2026-09-08») уникален —
    он и есть защита от повторов: два процесса или перезапуск контейнера
    не разошлют одно и то же дважды. Строка пишется ДО работы, поэтому
    упавшая задача остаётся видимой со статусом FAILED, а не исчезает.
    """

    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[ShortStr] = mapped_column(nullable=False)
    #: Задача + местная дата, на которую она была назначена.
    run_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    #: RUNNING → DONE / FAILED / SKIPPED. SKIPPED — окно наверстывания
    #: прошло: напоминание в полночь никому не нужно, но повторно
    #: запускать задачу за этот день уже не нужно тоже.
    status: Mapped[ShortStr] = mapped_column(nullable=False, default="RUNNING")
    started_at: Mapped[CreatedAt]
    finished_at: Mapped[Timestamp | None]
    #: Что сделано: «5 напоминаний» или текст ошибки.
    details: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_job_runs_job", "job", "started_at"),)


__all__ = [
    "AuditLog",
    "Base",
    "Employee",
    "EmployeeRole",
    "EventKind",
    "ExpenseLine",
    "ExpenseRequest",
    "JobRun",
    "MonthlyBudget",
    "Payment",
    "PaymentMethod",
    "Project",
    "RecoveryCode",
    "RequestEvent",
    "REQUEST_NUMBER_SEQ",
    "RequestStatus",
]
