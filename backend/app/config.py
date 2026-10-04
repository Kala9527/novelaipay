from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / '.env', extra='ignore')

    app_secret_key: str
    upstream_key_encryption_key: str
    payment_webhook_secret: str
    db_host: str = 'db'
    db_port: int = 5432
    postgres_db: str = 'novelaipay'
    postgres_user: str = 'novelaipay'
    postgres_password: str = ''
    database_url: str | None = None
    admin_email: str = 'admin@example.com'
    admin_password: str = ''
    allow_registration: bool = False
    cookie_secure: bool = True
    upstream_timeout_seconds: int = 120
    job_lease_seconds: int = 180
    job_poll_seconds: int = 3

    @property
    def sqlalchemy_url(self) -> URL | str:
        if self.database_url:
            return self.database_url
        return URL.create(
            'postgresql+psycopg',
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.db_host,
            port=self.db_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
