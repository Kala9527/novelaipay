import secrets
import hmac
import smtplib
from datetime import timedelta
from cryptography.fernet import InvalidToken

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_business_config, get_settings
from ..db import get_db
from ..models import RegistrationCode, User, utcnow
from ..registration_email import code_digest, email_ready, new_code, registration_settings, send_email
from ..security import create_session, hash_password, verify_password
from .deps import csrf_user, current_user


router = APIRouter(prefix='/api/auth', tags=['auth'])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class Registration(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    code: str = Field(pattern=r'^\d{6}$')


class CodeRequest(BaseModel):
    email: EmailStr


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=12, max_length=200)


def user_view(user: User) -> dict:
    return {
        'id': user.id, 'email': user.email, 'name': user.display_name,
        'role': 'admin' if user.is_admin else 'user', 'is_admin': user.is_admin,
        'max_concurrency': user.max_concurrency,
        'balance': str(user.balance), 'reserved': str(user.reserved),
    }


def set_auth_cookies(response: Response, user: User) -> None:
    secure = get_settings().cookie_secure
    response.set_cookie('nvp_session', create_session(user.id, user.session_version), httponly=True,
                        secure=secure, samesite='lax', max_age=43200)
    response.set_cookie('nvp_csrf', secrets.token_urlsafe(24), httponly=False,
                        secure=secure, samesite='lax', max_age=43200)


@router.get('/options')
def options(db: Session = Depends(get_db)) -> dict:
    settings = registration_settings(db)
    return {'registration_enabled': settings.enabled, 'email_configured': email_ready(settings),
            'code_expiry_minutes': settings.code_expiry_minutes}


@router.post('/registration-code')
def request_registration_code(payload: CodeRequest, db: Session = Depends(get_db)) -> dict:
    settings = registration_settings(db)
    if not settings.enabled:
        raise HTTPException(403, 'Registration disabled')
    if not email_ready(settings):
        raise HTTPException(503, 'Registration email is not configured')
    email = payload.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, 'Email already registered')
    now = utcnow()
    existing = db.get(RegistrationCode, email)
    if existing and existing.sent_at.replace(tzinfo=existing.sent_at.tzinfo or now.tzinfo) > now - timedelta(seconds=60):
        raise HTTPException(429, 'Please wait 60 seconds before requesting another code')
    code = new_code()
    expires_at = now + timedelta(minutes=settings.code_expiry_minutes)
    try:
        send_email(settings, email, code, expires_at)
    except (OSError, smtplib.SMTPException, ValueError, InvalidToken):
        raise HTTPException(502, 'Verification email could not be sent')
    if existing:
        existing.code_hash = code_digest(email, code)
        existing.expires_at = expires_at
        existing.sent_at = now
        existing.attempts = 0
    else:
        db.add(RegistrationCode(email=email, code_hash=code_digest(email, code),
                                expires_at=expires_at, sent_at=now, attempts=0))
    db.commit()
    return {'ok': True}


@router.post('/register')
def register(payload: Registration, response: Response, db: Session = Depends(get_db)) -> dict:
    settings = registration_settings(db)
    if not settings.enabled:
        raise HTTPException(403, 'Registration disabled')
    if not payload.name.strip():
        raise HTTPException(422, 'Name required')
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, 'Email already registered')
    issued = db.get(RegistrationCode, email)
    now = utcnow()
    if not issued or issued.expires_at.replace(tzinfo=issued.expires_at.tzinfo or now.tzinfo) <= now or issued.attempts >= 5:
        raise HTTPException(400, 'Verification code expired or unavailable')
    if not hmac.compare_digest(issued.code_hash, code_digest(email, payload.code)):
        issued.attempts += 1
        db.commit()
        raise HTTPException(400, 'Invalid verification code')
    user = User(email=email, display_name=payload.name.strip(),
                password_hash=hash_password(payload.password),
                max_concurrency=get_business_config().registration.default_max_concurrency)
    db.add(user)
    db.delete(issued)
    db.commit()
    db.refresh(user)
    set_auth_cookies(response, user)
    return user_view(user)


@router.post('/login')
def login(payload: Credentials, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not user.is_active or user.deleted_at or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, 'Invalid credentials')
    set_auth_cookies(response, user)
    return user_view(user)


@router.post('/logout')
def logout(response: Response, _: User = Depends(csrf_user)) -> dict:
    response.delete_cookie('nvp_session')
    response.delete_cookie('nvp_csrf')
    return {'ok': True}


@router.get('/me')
def me(user: User = Depends(current_user)) -> dict:
    return user_view(user)


@router.patch('/me')
def update_profile(payload: ProfileUpdate, response: Response, user: User = Depends(csrf_user),
                   db: Session = Depends(get_db)) -> dict:
    if payload.name is None and payload.new_password is None:
        raise HTTPException(422, 'Name or password required')
    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(422, 'Name required')
        user.display_name = payload.name.strip()
    if payload.new_password is not None:
        if not payload.current_password or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(403, 'Current password is incorrect')
        user.password_hash = hash_password(payload.new_password)
        user.session_version += 1
    db.commit()
    db.refresh(user)
    if payload.new_password is not None:
        set_auth_cookies(response, user)
    return user_view(user)
