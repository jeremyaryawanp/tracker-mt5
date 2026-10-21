from functools import lru_cache
from ipaddress import ip_address

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SESSIONS = (
    "ASIA=Asia/Tokyo,00:00,09:00;"
    "LONDON=Europe/London,08:00,17:00;"
    "NEW_YORK=America/New_York,08:00,17:00"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = Field(default="dev-insecure-secret-key-change-me", min_length=16)
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "sqlite:///./data/tradejournal.db"
    auto_migrate: bool = True

    display_timezone: str = "Asia/Jakarta"
    week_start: str = "MONDAY"
    trading_sessions: str = DEFAULT_SESSIONS
    overtrading_daily_threshold: int = 8

    admin_username: str = "admin"
    admin_password_hash: str = ""

    ingest_max_bytes: int = 10_000_000
    ingest_rate_limit_per_minute: int = 30

    llm_reviews_enabled: bool = False
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    log_level: str = "INFO"
    log_json: bool = True

    @property
    def is_loopback_host(self) -> bool:
        if self.app_host in ("localhost",):
            return True
        try:
            return ip_address(self.app_host).is_loopback
        except ValueError:
            return False

    @property
    def auth_enabled(self) -> bool:
        return bool(self.admin_password_hash)

    def validate_runtime(self) -> None:
        if not self.is_loopback_host and not self.auth_enabled:
            raise RuntimeError(
                "APP_HOST is not a loopback address: set ADMIN_PASSWORD_HASH "
                "(see scripts/hash_password.py) before exposing the app."
            )
        if self.app_env == "production" and self.app_secret_key.startswith("dev-insecure"):
            raise RuntimeError("APP_SECRET_KEY must be set in production.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
