import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_business_config, get_settings
from ..db import get_db
from ..models import User
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
def options() -> dict:
    return {'registration_enabled': get_business_config().registration.enabled}


@router.post('/register')
def register(payload: Registration, response: Response, db: Session = Depends(get_db)) -> dict:
    registration = get_business_config().registration
    if not registration.enabled:
        raise HTTPException(403, 'Registration disabled')
    if not payload.name.strip():
        raise HTTPException(422, 'Name required')
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(409, 'Email already registered')
    user = User(email=payload.email.lower(), display_name=payload.name.strip(),
                password_hash=hash_password(payload.password),
                max_concurrency=registration.default_max_concurrency)
    db.add(user)
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
