import hmac

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..group_access import can_use_group
from ..models import ApiKey, UpstreamGroup, User
from ..security import decode_session, hash_api_key


def current_user(
    session: str | None = Cookie(default=None, alias='nvp_session'),
    db: Session = Depends(get_db),
) -> User:
    user_id = decode_session(session) if session else None
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active or user.deleted_at:
        raise HTTPException(401, 'Sign in required')
    return user


def csrf_user(
    user: User = Depends(current_user),
    cookie: str | None = Cookie(default=None, alias='nvp_csrf'),
    header: str | None = Header(default=None, alias='X-CSRF-Token'),
) -> User:
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(403, 'Invalid CSRF token')
    return user


def admin_user(user: User = Depends(csrf_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, 'Admin access required')
    return user


def downstream_key(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ApiKey:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'API key required')
    raw = authorization[7:]
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw)))
    if key is None or key.revoked_at or not key.user.is_active or key.user.deleted_at or not can_use_group(
        db, db.get(UpstreamGroup, key.group_id), key.user_id
    ):
        raise HTTPException(401, 'Invalid API key')
    return key
