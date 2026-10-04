import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet

from .config import get_settings


password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, stored: str) -> bool:
    try:
        return password_hasher.verify(stored, password)
    except (VerifyMismatchError, ValueError):
        return False


def new_api_key() -> tuple[str, str, str]:
    key = 'nvp_' + secrets.token_urlsafe(32)
    return key, key[:12], hash_api_key(key)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_session(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {'sub': str(user_id), 'iat': now, 'exp': now + timedelta(hours=12), 'type': 'session'},
        get_settings().app_secret_key,
        algorithm='HS256',
    )


def decode_session(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_settings().app_secret_key, algorithms=['HS256'])
        return int(payload['sub']) if payload.get('type') == 'session' else None
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None


def encrypt_upstream_key(value: str) -> str:
    return Fernet(get_settings().upstream_key_encryption_key.encode()).encrypt(value.encode()).decode()


def decrypt_upstream_key(value: str) -> str:
    return Fernet(get_settings().upstream_key_encryption_key.encode()).decrypt(value.encode()).decode()
