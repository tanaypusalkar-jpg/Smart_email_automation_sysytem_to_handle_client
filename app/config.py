"""
Centralized app configuration.

Everything is read from environment variables (or a .env file in dev).
Never hardcode secrets here - this file just defines what's expected.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Claude API
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "Email Automation Bot"

    # IMAP (optional)
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""

    # Database
    database_url: str = "sqlite:///./app/data/emails.db"

    # Google OAuth - blank means the auth check is skipped (dev/test mode)
    google_client_id: str = ""

    # Rate limiting (slowapi syntax, e.g. "5/minute")
    rate_limit_send: str = "5/minute"
    rate_limit_compose: str = "20/minute"

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    vector_db_path: str = "./app/data/chroma_store"

    # Safety switch: when true, /send does NOT actually dispatch email,
    # it just returns what would have been sent. Flip to false only when
    # SMTP creds are confirmed working.
    dry_run: bool = True

    @property
    def oauth_enabled(self) -> bool:
        return bool(self.google_client_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
