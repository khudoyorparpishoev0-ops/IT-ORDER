"""Единственная точка чтения переменных окружения."""

from functools import lru_cache
from urllib.parse import quote

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
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
