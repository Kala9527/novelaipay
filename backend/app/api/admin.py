from decimal import Decimal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import GenerationJob, ModelMapping, PriceVersion, UpstreamAccount, User
from ..security import encrypt_upstream_key, hash_password
from ..services import credit_wallet, resolve_uncertain
from .deps import admin_user
from .user import job_view


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
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)


class Resolution(BaseModel):
    succeeded: bool
    image_url: str | None = None
    note: str | None = Field(default=None, max_length=500)


@router.get('/users')
def users(_: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[dict]:
    return [{'id': u.id, 'email': u.email, 'balance': str(u.balance),
             'reserved': str(u.reserved), 'is_active': u.is_active}
            for u in db.scalars(select(User).order_by(User.id.desc()).limit(100))]


@router.post('/users')
def create_user(payload: UserCreate, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, 'Email already exists')
    row = User(email=email, password_hash=hash_password(payload.password))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {'id': row.id, 'email': row.email}


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
