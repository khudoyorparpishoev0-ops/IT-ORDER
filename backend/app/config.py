"""Единственная точка чтения переменных окружения."""

from functools import lru_cache

from pydantic import Field, PostgresDsn, computed_field
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

    # --- Безопасность (используется с фазы 3) ---
    secret_key: str = ""

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
