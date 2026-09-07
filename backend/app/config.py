"""Единственная точка чтения переменных окружения."""

from functools import lru_cache

from pydantic import Field, PostgresDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Приложение ---
    app_name: str = "HONA CORE"
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
    auto_approve_threshold: str = Field(
        default="500.00",
        description=(
            "Порог автоодобрения в сомони. Заявка на сумму не выше порога "
            "одобряется без участия руководителя. Значение по умолчанию "
            "взято из макета и подлежит подтверждению заказчиком."
        ),
    )
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
        default="it-hona.tj",
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
        default="IT-HONA CORE",
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

    #: Первый администратор создаётся при старте, если в базе нет ни одного.
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_name: str = "Администратор"

    @computed_field
    @property
    def database_url(self) -> str:
        """DSN для SQLAlchemy. Пароль сюда попадает, в логи — нет."""
        dsn = PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.postgres_db,
        )
        return str(dsn)

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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
