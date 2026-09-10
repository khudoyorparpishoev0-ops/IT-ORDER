"""Единственная точка чтения переменных окружения."""

from decimal import Decimal
from functools import lru_cache
from urllib.parse import quote

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Пробелы и переводы строк по краям значений срезаются. Проект
        # переносят на сервер через Windows, и .env приезжает с CRLF:
        # невидимый «\r» попадал в токен бота и в пароль SMTP, после чего
        # Telegram отвечал «malformed URL», а почта — отказом в логине.
        # Ловить это по симптомам дорого, срезать — одна строка.
        str_strip_whitespace=True,
    )

    # --- Приложение ---
    app_name: str = "HONA ORDER"
    app_env: str = Field(default="production", description="production | development")
    app_timezone: str = Field(
        default="Asia/Dushanbe",
        description="Пояс бизнес-логики. В базе всё хранится в UTC.",
    )
    log_level: str = "INFO"

    # --- База данных ---
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "hona_core"
    postgres_user: str = "hona"
    postgres_password: str = ""

    # --- Правила согласования ---
    request_number_prefix: str = Field(
        default="РЗ",
        description="Префикс номера заявки: РЗ-2419.",
    )

    # --- Безопасность ---
    secret_key: str = Field(
        default="",
        description=(
            "Секрет подписи сессий. Обязателен в production: без него "
            "приложение не стартует. Генерация: openssl rand -hex 32"
        ),
    )
    session_lifetime_minutes: int = Field(
        default=12 * 60,
        ge=5,
        description="Срок жизни сессии. Рабочий день плюс запас.",
    )
    cookie_name: str = "hona_session"
    cookie_secure: bool = Field(
        default=True,
        description=(
            "Отдавать cookie только по HTTPS. В локальной разработке по HTTP "
            "поставить false, иначе браузер cookie не сохранит."
        ),
    )
    allowed_email_domains: str = Field(
        default="ithona.tj",
        description=(
            "Домены корпоративной почты через запятую. Войти и завести "
            "сотрудника можно только с адресом из этого списка. Пустая "
            "строка снимает ограничение — так делать не рекомендуется."
        ),
    )

    require_2fa_roles: str = Field(
        default="admin,finance",
        description=(
            "Роли, которым двухфакторный вход обязателен: без него они не "
            "получат сессию. Остальные могут включить его добровольно. "
            "Пустая строка — никого не принуждаем, 'all' — всех."
        ),
    )
    totp_issuer: str = Field(
        default="IT-HONA ORDER",
        description="Название системы в приложении-аутентификаторе.",
    )
    max_failed_logins: int = Field(
        default=8,
        ge=3,
        description=(
            "Сколько неудачных попыток подряд до временной блокировки. "
            "Без этого шестизначный код TOTP перебирается за часы."
        ),
    )
    lockout_minutes: int = Field(
        default=15, ge=1, description="Насколько блокируется вход после серии ошибок."
    )

    # --- Почта (Zoho Mail) ---
    smtp_host: str = Field(
        default="smtp.zoho.com",
        description=(
            "SMTP-сервер. У Zoho он зависит от региона аккаунта: "
            "smtp.zoho.com (США), smtp.zoho.eu (Европа), smtp.zoho.in (Индия), "
            "smtp.zoho.com.au, smtp.zohocloud.ca. Неверный регион даёт "
            "ошибку аутентификации, хотя логин и пароль правильные."
        ),
    )
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_security: str = Field(
        default="ssl",
        description="ssl (порт 465) или starttls (порт 587). У Zoho работают оба.",
    )
    smtp_user: str = Field(
        default="",
        description="Полный адрес ящика: у Zoho логин — это адрес целиком.",
    )
    smtp_password: str = Field(
        default="",
        description=(
            "Пароль приложения из Zoho, а не пароль от аккаунта. Если у "
            "аккаунта включён второй фактор — обычный пароль SMTP не примет."
        ),
    )
    mail_from: str = Field(
        default="",
        description=(
            "Адрес отправителя. Должен принадлежать проверенному домену "
            "Zoho, иначе письма будут отклонены. Пусто — берётся SMTP_USER."
        ),
    )
    mail_from_name: str = "IT-HONA ORDER"
    smtp_timeout_seconds: int = Field(default=15, ge=1)

    # --- Telegram ---
    telegram_bot_token: str = Field(
        default="",
        description=(
            "Токен бота от @BotFather. Пусто — уведомления в Telegram "
            "выключены, всё остальное работает как раньше."
        ),
    )
    telegram_bot_username: str = Field(
        default="",
        description=(
            "Имя бота без @ — из него собирается ссылка привязки "
            "https://t.me/<имя>?start=<код>."
        ),
    )
    telegram_timeout_seconds: int = Field(default=10, ge=1)

    # --- Push-уведомления в браузер (телефон с панелью на экране) ---
    vapid_private_key: str = Field(
        default="",
        description=(
            "Закрытый ключ VAPID (base64url, 43 символа). Сгенерировать: "
            "python -m app.push_setup. Пусто — push выключен, всё остальное "
            "работает как раньше. Смена ключа обнуляет все подписки: "
            "телефоны перестанут получать уведомления, пока люди не включат "
            "их заново."
        ),
    )
    vapid_subject: str = Field(
        default="",
        description=(
            "Контакт для push-служб браузеров: mailto:адрес или https://адрес. "
            "По нему Google или Apple напишут, если сервер шлёт мусор. "
            "Пусто — берётся MAIL_FROM или ACME_EMAIL."
        ),
    )
    push_ttl_seconds: int = Field(
        default=86400,
        ge=60,
        description="Сколько push-служба хранит уведомление для выключенного телефона.",
    )
    push_timeout_seconds: int = Field(default=10, ge=1)

    # --- Помощник по материалам (Claude) ---
    anthropic_api_key: str = Field(
        default="",
        description=(
            "Ключ Claude API (console.anthropic.com). Пусто — помощник "
            "выключен: форма заявки подсказывает только то, что уже "
            "заказывали, всё остальное работает как раньше."
        ),
    )
    assistant_model: str = Field(
        default="claude-opus-5",
        description="Модель Claude для помощника по материалам.",
    )
    assistant_timeout_seconds: int = Field(
        default=90,
        ge=5,
        le=300,
        description=(
            "Сколько ждать ответа помощника. Разбор потребности в диалоге "
            "занимает десятки секунд: 20 секунд не хватало, и подсказка "
            "выглядела как «помощник недоступен»."
        ),
    )
    ai_interactions_retention_days: int = Field(
        default=180,
        ge=7,
        le=3650,
        description=(
            "Сколько хранить журнал обращений к AI. Он вспомогательный: по "
            "нему видно, помогает помощник или мешает, и больше ничего. "
            "Заявки, их текст, журнал действий и история статусов от чистки "
            "не зависят вовсе — они лежат в других таблицах и не связаны с "
            "этой. Чистит фоновая задача раз в сутки."
        ),
    )
    analytics_prompt_file: str = Field(
        default="",
        description=(
            "Файл с правилами AI-аналитика для руководителя. Пусто — "
            "встроенный текст. Позволяет менять правила без пересборки."
        ),
    )

    stale_hours: int = Field(
        default=24,
        ge=1,
        le=720,
        description=(
            "Со скольких часов заявка считается стоящей без движения. "
            "Отдельно от нормативов этапа: заявка может укладываться в "
            "норматив закупа и всё равно стоять сутки — руководителю это "
            "стоит увидеть."
        ),
    )

    # --- Расход на AI ---
    ai_prices_file: str = Field(
        default="",
        description=(
            "Файл с ценами моделей (JSON). Пусто — встроенная таблица. "
            "Anthropic меняет прайс чаще, чем мы выкатываем релизы."
        ),
    )
    ai_monthly_budget_usd: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        description=(
            "Ожидаемый расход на AI за месяц, доллары. 0 — бюджет не задан "
            "и предупреждать не о чем. Помощник по достижении бюджета НЕ "
            "выключается: это решение человека, а не порога."
        ),
    )
    ai_budget_warning_percent: int = Field(
        default=80,
        ge=1,
        le=100,
        description="При какой доле бюджета предупреждать администратора.",
    )

    # --- Автоматические сводки ORDER Intelligence ---
    intelligence_scan_minutes: int = Field(
        default=20,
        ge=5,
        le=720,
        description=(
            "Как часто искать критичные проблемы для сигналов. Чаще пяти "
            "минут смысла нет: заявка не становится критичной за минуту, а "
            "лишний проход — это запросы к базе на ровном месте."
        ),
    )
    critical_alert_repeat_hours: int = Field(
        default=12,
        ge=1,
        le=168,
        description=(
            "Через сколько часов напомнить о неустранённой критичной "
            "проблеме. Напоминание, приходящее слишком часто, перестаёт "
            "быть напоминанием."
        ),
    )

    # --- Нормативы времени на этапах (часы). Аналитика сравнивает с ними ---
    sla_pending_hours: int = Field(
        default=8, ge=1, le=720, description="Согласование покупки руководителем."
    )
    sla_sourcing_hours: int = Field(
        default=24, ge=1, le=720, description="Проверка склада и цены отделом закупа."
    )
    sla_priced_hours: int = Field(
        default=8, ge=1, le=720, description="Утверждение суммы руководителем."
    )
    sla_approved_hours: int = Field(
        default=24, ge=1, le=720, description="Выплата бухгалтерией."
    )

    assistant_prompt_file: str = Field(
        default="",
        description=(
            "Путь к файлу с системным промптом помощника. Пусто — берётся "
            "встроенный текст. Файл позволяет править правила помощника на "
            "сервере, не пересобирая образ."
        ),
    )

    # --- Планировщик ---
    scheduler_enabled: bool = Field(
        default=True,
        description=(
            "Фоновые задачи: напоминания о залежавшихся заявках и недельная "
            "сводка. Выключается на время диагностики."
        ),
    )
    stale_request_days: int = Field(
        default=3,
        ge=1,
        description="Со скольких суток на одном шаге заявка считается залежавшейся.",
    )
    reminder_hour: int = Field(
        default=9,
        ge=0,
        le=23,
        description="Час по местному времени, когда уходят напоминания и сводка.",
    )
    scheduler_catch_up_hours: int = Field(
        default=6,
        ge=1,
        le=23,
        description=(
            "Сколько часов после назначенного времени задачу ещё имеет смысл "
            "выполнить. Сервер лежал до вечера — напоминание в полночь никому "
            "не нужно, день помечается пропущенным."
        ),
    )
    scheduler_tick_seconds: int = Field(default=60, ge=5, le=3600)

    public_base_url: str = Field(
        default="",
        description=(
            "Адрес панели снаружи, например https://order.ithona.tj. "
            "Нужен для ссылок в письмах: без него ссылку восстановления "
            "пароля некуда вести."
        ),
    )
    password_reset_ttl_minutes: int = Field(
        default=30,
        ge=5,
        description="Срок жизни ссылки восстановления пароля.",
    )

    #: Первый администратор создаётся при старте, если в базе нет ни одного.
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_name: str = "Администратор"

    @computed_field
    @property
    def database_url(self) -> str:
        """DSN для SQLAlchemy. Пароль сюда попадает, в логи — нет.

        Логин и пароль экранируются: случайный пароль из `openssl rand
        -base64` содержит «/», «+» и «=», а они значимы в URL. Без
        экранирования «/» обрывает адрес хоста, и приложение падает
        на старте с невнятной ошибкой разбора порта.
        """
        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password, safe="")
        host = self.postgres_host
        # Unix-сокет тоже начинается со «/» и требует экранирования.
        if host.startswith("/"):
            host = quote(host, safe="")
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{host}:{self.postgres_port}/{quote(self.postgres_db, safe='')}"
        )

    @computed_field
    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @computed_field
    @property
    def email_domains(self) -> tuple[str, ...]:
        """Разрешённые домены в нижнем регистре. Пустой кортеж — без проверки."""
        return tuple(
            d.strip().lower().lstrip("@")
            for d in self.allowed_email_domains.split(",")
            if d.strip()
        )

    @computed_field
    @property
    def mail_enabled(self) -> bool:
        """Почта настроена. Без неё письма не отправляются, а функции,
        которые на них опираются, честно сообщают об этом."""
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @computed_field
    @property
    def mail_sender(self) -> str:
        return self.mail_from or self.smtp_user

    @computed_field
    @property
    def telegram_enabled(self) -> bool:
        """Уведомления в Telegram настроены. Без токена бот молчит, но
        ничего не ломает: почта и панель работают сами по себе."""
        return bool(self.telegram_bot_token)

    @computed_field
    @property
    def push_enabled(self) -> bool:
        """Push в браузер настроен: есть закрытый ключ VAPID."""
        return bool(self.vapid_private_key)

    @computed_field
    @property
    def assistant_enabled(self) -> bool:
        """Помощник по материалам настроен: задан ключ Claude API."""
        return bool(self.anthropic_api_key)

    @property
    def push_subject(self) -> str:
        """Контакт в подписи VAPID. Обязателен по стандарту — без него
        push-службы отвечают 400 или 403."""
        if self.vapid_subject:
            return self.vapid_subject
        contact = self.mail_from or self.smtp_user
        if contact:
            return f"mailto:{contact}"
        if self.public_base_url:
            return self.public_base_url
        return "mailto:admin@example.com"

    @property
    def telegram_webhook_secret(self) -> str:
        """Секрет в адресе вебхука. Выводится из SECRET_KEY, чтобы не
        заводить ещё одну переменную: адрес знает только Telegram.

        Не computed_field намеренно: вычисляемые поля попадают в
        model_dump и в repr настроек, а секрету там не место.
        """
        from hashlib import sha256

        source = f"telegram-webhook:{self.secret_key}:{self.telegram_bot_token}"
        return sha256(source.encode("utf-8")).hexdigest()[:32]

    @computed_field
    @property
    def roles_requiring_2fa(self) -> frozenset[str]:
        """Роли с обязательной двухфакторной аутентификацией."""
        raw = {r.strip().lower() for r in self.require_2fa_roles.split(",") if r.strip()}
        if "all" in raw:
            return frozenset({"employee", "manager", "finance", "admin"})
        return frozenset(raw)

    @model_validator(mode="after")
    def check_production_secrets(self) -> "Settings":
        """В production пустой secret_key означает, что любой сможет
        подписать себе токен администратора. Падаем на старте, а не потом."""
        if not self.is_development and not self.secret_key:
            raise ValueError(
                "SECRET_KEY не задан. Сгенерируйте: openssl rand -hex 32"
            )
        if self.smtp_security not in ("ssl", "starttls"):
            raise ValueError("SMTP_SECURITY должен быть ssl или starttls")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
