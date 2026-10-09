import binascii
from functools import lru_cache
from pathlib import Path

import yaml
from cryptography.fernet import Fernet
from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator
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
    config_file: Path = Path(__file__).resolve().parents[2] / 'config.yaml'
    cookie_secure: bool = True
    upstream_timeout_seconds: int = 120
    job_lease_seconds: int = 180
    job_poll_seconds: int = 3
    cors_allowed_origins: str = 'http://127.0.0.1:8009,http://localhost:8009'

    @field_validator('upstream_key_encryption_key')
    @classmethod
    def validate_upstream_key_encryption_key(cls, value: str) -> str:
        try:
            Fernet(value.encode())
        except (ValueError, binascii.Error) as exc:
            raise ValueError(
                'UPSTREAM_KEY_ENCRYPTION_KEY must be a Fernet key (32 URL-safe base64-encoded bytes); '
                'generate one with Fernet.generate_key() and keep the existing key if data is already encrypted'
            ) from exc
        return value

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


class AdminConfig(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=200)
    max_concurrency: int = Field(default=5, ge=1, le=100)


class RegistrationConfig(BaseModel):
    enabled: bool = True
    default_max_concurrency: int = Field(default=2, ge=1, le=100)


class BusinessConfig(BaseModel):
    admin: AdminConfig
    registration: RegistrationConfig = RegistrationConfig()


@lru_cache
def get_business_config() -> BusinessConfig:
    path = get_settings().config_file
    if not path.is_file():
        raise RuntimeError(f'Missing {path}; copy config.example.yaml to config.yaml')
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        return BusinessConfig.model_validate(data)
    except (yaml.YAMLError, ValidationError) as exc:
        raise RuntimeError(f'Invalid business configuration: {path}') from exc
