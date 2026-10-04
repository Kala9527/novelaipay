from decimal import Decimal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ApiKey, GenerationJob, JobStatus, ModelMapping, PriceVersion, UpstreamAccount, User, utcnow
from ..security import encrypt_upstream_key, hash_password, new_api_key
from ..services import credit_wallet, resolve_uncertain
from .deps import admin_user
from .user import job_view, key_view


router = APIRouter(prefix='/api/admin', tags=['admin'])


class UpstreamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(max_length=500)
    api_key: str = Field(min_length=1)


class MappingUpsert(BaseModel):
    public_name: str = Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$')
    upstream_account_id: int
    upstream_model: str = Field(min_length=1, max_length=150)
    price: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    max_concurrency: int = Field(default=2, ge=1, le=100)
    enabled: bool = True


class CreditRequest(BaseModel):
    user_id: int
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    reference: str = Field(min_length=1, max_length=80)


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    max_concurrency: int = Field(default=2, ge=1, le=100)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    max_concurrency: int | None = Field(default=None, ge=1, le=100)
    is_active: bool | None = None


class KeyIssue(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class Resolution(BaseModel):
    succeeded: bool
    image_url: str | None = None
    note: str | None = Field(default=None, max_length=500)


@router.get('/users')
def users(include_deleted: bool = False, _: User = Depends(admin_user),
          db: Session = Depends(get_db)) -> list[dict]:
    query = select(User)
    if not include_deleted:
        query = query.where(User.deleted_at.is_(None))
    return [{'id': u.id, 'name': u.display_name, 'email': u.email,
             'role': 'admin' if u.is_admin else 'user', 'is_admin': u.is_admin,
             'balance': str(u.balance), 'reserved': str(u.reserved),
             'max_concurrency': u.max_concurrency, 'is_active': u.is_active,
             'deleted_at': u.deleted_at}
            for u in db.scalars(query.order_by(User.id.desc()).limit(100))]


@router.post('/users')
def create_user(payload: UserCreate, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    email = payload.email.strip().lower()
    if not payload.name.strip():
        raise HTTPException(422, 'Name required')
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, 'Email already exists')
    row = User(email=email, display_name=payload.name.strip(),
               password_hash=hash_password(payload.password),
               max_concurrency=payload.max_concurrency)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {'id': row.id, 'email': row.email, 'name': row.display_name}


@router.patch('/users/{user_id}')
def update_user(user_id: int, payload: UserUpdate, _: User = Depends(admin_user),
                db: Session = Depends(get_db)) -> dict:
    db.commit()
    with db.begin():
        row = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if row is None:
            raise HTTPException(404, 'User not found')
        if row.is_admin:
            raise HTTPException(403, 'Administrator is managed through config.yaml')
        if row.deleted_at:
            if payload.is_active is not True:
                raise HTTPException(409, 'Restore user before editing')
            row.deleted_at = None
        if payload.name is not None:
            if not payload.name.strip():
                raise HTTPException(422, 'Name required')
            row.display_name = payload.name.strip()
        if payload.max_concurrency is not None:
            row.max_concurrency = payload.max_concurrency
        if payload.is_active is not None:
            row.is_active = payload.is_active
    return {'ok': True}


@router.delete('/users/{user_id}')
def delete_user(user_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    db.commit()
    with db.begin():
        row = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if row is None or row.deleted_at:
            raise HTTPException(404, 'User not found')
        if row.is_admin:
            raise HTTPException(403, 'Administrator cannot be deleted')
        active = db.scalar(select(func.count()).select_from(GenerationJob).where(
            GenerationJob.user_id == row.id,
            GenerationJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.UNCERTAIN]),
        ))
        if active or row.reserved:
            raise HTTPException(409, 'Resolve active jobs before deleting user')
        row.is_active = False
        row.deleted_at = utcnow()
        for key in db.scalars(select(ApiKey).where(ApiKey.user_id == row.id, ApiKey.revoked_at.is_(None))):
            key.revoked_at = utcnow()
    return {'ok': True}


@router.get('/users/{user_id}/keys')
def user_keys(user_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[dict]:
    row = db.get(User, user_id)
    if row is None or row.deleted_at:
        raise HTTPException(404, 'User not found')
    return [key_view(key) for key in db.scalars(select(ApiKey).where(
        ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None),
    ).order_by(ApiKey.id.desc()))]


@router.post('/users/{user_id}/keys')
def issue_user_key(user_id: int, payload: KeyIssue, _: User = Depends(admin_user),
                   db: Session = Depends(get_db)) -> dict:
    row = db.get(User, user_id)
    if row is None or row.deleted_at or not row.is_active:
        raise HTTPException(404, 'Active user not found')
    raw, prefix, digest = new_api_key()
    key = ApiKey(user_id=row.id, name=payload.name, prefix=prefix, key_hash=digest)
    db.add(key)
    db.commit()
    db.refresh(key)
    return {**key_view(key), 'key': raw}


@router.delete('/users/{user_id}/keys/{key_id}')
def revoke_user_key(user_id: int, key_id: int, _: User = Depends(admin_user),
                    db: Session = Depends(get_db)) -> dict:
    key = db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id))
    if key is None:
        raise HTTPException(404, 'Key not found')
    key.revoked_at = utcnow()
    db.commit()
    return {'ok': True}


@router.post('/credit')
def credit(payload: CreditRequest, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    credit_wallet(db, payload.user_id, payload.amount, f'admin:{payload.reference}', 'admin_credit')
    return {'ok': True}


@router.get('/upstreams')
def upstreams(_: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[dict]:
    return [{'id': row.id, 'name': row.name, 'base_url': row.base_url, 'enabled': row.enabled}
            for row in db.scalars(select(UpstreamAccount).order_by(UpstreamAccount.id))]


@router.post('/upstreams')
def create_upstream(payload: UpstreamCreate, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    parsed = urlparse(payload.base_url)
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')):
        raise HTTPException(422, 'Upstream URL must use HTTPS')
    if parsed.username or parsed.password or not parsed.hostname or parsed.query or parsed.fragment:
        raise HTTPException(422, 'Invalid upstream URL')
    if db.scalar(select(UpstreamAccount).where(UpstreamAccount.name == payload.name)):
        raise HTTPException(409, 'Upstream name exists')
    account = UpstreamAccount(name=payload.name, base_url=payload.base_url.rstrip('/'),
                              encrypted_key=encrypt_upstream_key(payload.api_key))
    db.add(account)
    db.commit()
    db.refresh(account)
    return {'id': account.id, 'name': account.name, 'base_url': account.base_url}


@router.get('/mappings')
def mappings(_: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[dict]:
    result = []
    for row in db.scalars(select(ModelMapping).order_by(ModelMapping.id)):
        price = db.scalar(select(PriceVersion).where(PriceVersion.model_mapping_id == row.id).order_by(
            PriceVersion.id.desc(),
        ))
        result.append({'id': row.id, 'public_name': row.public_name,
                       'upstream_account_id': row.upstream_account_id,
                       'upstream_model': row.upstream_model, 'enabled': row.enabled,
                       'max_concurrency': row.max_concurrency, 'revision': row.revision,
                       'price': str(price.amount) if price else None})
    return result


@router.post('/mappings')
def upsert_mapping(payload: MappingUpsert, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    account = db.get(UpstreamAccount, payload.upstream_account_id)
    if account is None:
        raise HTTPException(404, 'Upstream account not found')
    row = db.scalar(select(ModelMapping).where(ModelMapping.public_name == payload.public_name))
    if row is None:
        row = ModelMapping(public_name=payload.public_name, upstream_model=payload.upstream_model,
                           upstream_account_id=account.id, enabled=payload.enabled,
                           max_concurrency=payload.max_concurrency)
        db.add(row)
        db.flush()
    else:
        row.upstream_model = payload.upstream_model
        row.upstream_account_id = account.id
        row.enabled = payload.enabled
        row.max_concurrency = payload.max_concurrency
        row.revision += 1
    price = db.scalar(select(PriceVersion).where(PriceVersion.model_mapping_id == row.id).order_by(
        PriceVersion.id.desc(),
    ))
    if price is None or price.amount != payload.price:
        db.add(PriceVersion(model_mapping_id=row.id, amount=payload.price))
    db.commit()
    return {'id': row.id, 'revision': row.revision}


@router.get('/uncertain')
def uncertain(_: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[dict]:
    return [job_view(job) for job in db.scalars(select(GenerationJob).where(
        GenerationJob.status == 'uncertain',
    ).order_by(GenerationJob.created_at))]


@router.post('/uncertain/{job_id}/resolve')
def resolve(job_id: str, payload: Resolution, _: User = Depends(admin_user),
            db: Session = Depends(get_db)) -> dict:
    if payload.succeeded and not payload.image_url:
        raise HTTPException(422, 'Image URL required for successful job')
    result = {'data': [{'url': payload.image_url}]} if payload.succeeded else None
    resolve_uncertain(db, job_id, result, payload.note)
    return {'ok': True}
