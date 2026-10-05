from decimal import Decimal
from urllib.parse import urlparse
import httpx

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..config import get_settings
from ..models import ApiKey, GenerationJob, GroupAccount, JobStatus, ModelMapping, ModelRoute, PriceVersion, UpstreamAccount, UpstreamGroup, User, utcnow
from ..security import decrypt_upstream_key, encrypt_upstream_key, hash_password, new_api_key
from ..services import credit_wallet, resolve_uncertain
from ..upstream import UpstreamUncertain, store_remote_image
from .deps import admin_user
from .user import job_view, key_view


router = APIRouter(prefix='/api/admin', tags=['admin'])


def default_group(db: Session) -> UpstreamGroup:
    group = db.scalar(select(UpstreamGroup).order_by(UpstreamGroup.id))
    if group is None:
        group = UpstreamGroup(name='默认分组')
        db.add(group)
        db.flush()
    return group


class UpstreamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(max_length=500)
    api_key: str = Field(min_length=1)
    provider: str = Field(default='openai', pattern='^(openai|novelai)$')
    opus_free: bool = False
    max_concurrency: int = Field(default=10, ge=1, le=1000)


class UpstreamUpdate(BaseModel):
    max_concurrency: int = Field(ge=1, le=1000)
    enabled: bool


class GroupUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    max_concurrency: int = Field(default=10, ge=1, le=1000)
    account_ids: list[int] = Field(default_factory=list)
    enabled: bool = True


class RouteInput(BaseModel):
    account_id: int
    upstream_model: str = Field(min_length=1, max_length=150)


class MappingUpsert(BaseModel):
    public_name: str = Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$')
    group_id: int | None = None
    upstream_account_id: int | None = None
    upstream_model: str | None = None
    routes: list[RouteInput] = Field(default_factory=list)
    price: Decimal = Field(gt=0, max_digits=14, decimal_places=4)
    extra_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4)
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
    group_id: int | None = None


class Resolution(BaseModel):
    succeeded: bool
    image_url: str | None = None
    anlas_charged: int | None = Field(default=None, ge=0)
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
    group = db.get(UpstreamGroup, payload.group_id) if payload.group_id else default_group(db)
    if group is None or not group.enabled:
        raise HTTPException(404, 'Group unavailable')
    raw, prefix, digest = new_api_key()
    key = ApiKey(user_id=row.id, group_id=group.id, name=payload.name, prefix=prefix, key_hash=digest,
                 encrypted_key=encrypt_upstream_key(raw))
    db.add(key)
    db.commit()
    db.refresh(key)
    return {**key_view(key), 'key': raw}


@router.get('/users/{user_id}/keys/{key_id}/secret')
def copy_user_key(user_id: int, key_id: int, _: User = Depends(admin_user),
                  db: Session = Depends(get_db)) -> dict:
    key = db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id,
                                         ApiKey.revoked_at.is_(None)))
    if key is None or not key.encrypted_key:
        raise HTTPException(404, 'Key cannot be copied; create a new key')
    return {'key': decrypt_upstream_key(key.encrypted_key)}


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
    return [{'id': row.id, 'name': row.name, 'base_url': row.base_url,
             'provider': row.provider, 'opus_free': row.opus_free, 'enabled': row.enabled,
             'max_concurrency': row.max_concurrency}
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
                              encrypted_key=encrypt_upstream_key(payload.api_key),
                              provider=payload.provider, opus_free=payload.opus_free,
                              max_concurrency=payload.max_concurrency)
    db.add(account)
    group = default_group(db)
    db.flush()
    db.add(GroupAccount(group_id=group.id, account_id=account.id))
    db.commit()
    db.refresh(account)
    return {'id': account.id, 'name': account.name, 'base_url': account.base_url,
            'provider': account.provider, 'opus_free': account.opus_free,
            'max_concurrency': account.max_concurrency}


@router.patch('/upstreams/{account_id}')
def update_upstream(account_id: int, payload: UpstreamUpdate, _: User = Depends(admin_user),
                    db: Session = Depends(get_db)) -> dict:
    account = db.get(UpstreamAccount, account_id)
    if account is None:
        raise HTTPException(404, 'Upstream not found')
    account.max_concurrency = payload.max_concurrency
    account.enabled = payload.enabled
    db.commit()
    return {'ok': True}


@router.get('/upstreams/{account_id}/models')
def upstream_models(account_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    account = db.get(UpstreamAccount, account_id)
    if account is None:
        raise HTTPException(404, 'Upstream not found')
    if account.provider == 'novelai':
        # NovelAI does not expose a model-list endpoint.
        return {'models': ['nai-diffusion-4-curated-preview', 'nai-diffusion-4-full',
                           'nai-diffusion-4-5-curated', 'nai-diffusion-4-5-full',
                           'nai-diffusion-3'], 'source': 'supported'}
    try:
        response = httpx.get(account.base_url.rstrip('/') + '/models',
            headers={'Authorization': 'Bearer ' + decrypt_upstream_key(account.encrypted_key)},
            timeout=get_settings().upstream_timeout_seconds)
        response.raise_for_status()
        data = response.json().get('data', [])
        models = sorted({item['id'] for item in data if isinstance(item, dict)
                         and isinstance(item.get('id'), str)})
    except (httpx.HTTPError, ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(502, 'Could not retrieve upstream models') from exc
    return {'models': models, 'source': 'upstream'}


@router.get('/groups')
def groups(_: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[dict]:
    return [{'id': row.id, 'name': row.name, 'max_concurrency': row.max_concurrency,
             'enabled': row.enabled, 'account_ids': list(db.scalars(select(GroupAccount.account_id).where(
                 GroupAccount.group_id == row.id).order_by(GroupAccount.id)))}
            for row in db.scalars(select(UpstreamGroup).order_by(UpstreamGroup.id))]


@router.post('/groups')
def save_group(payload: GroupUpsert, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(UpstreamGroup).where(UpstreamGroup.name == payload.name))
    if row is None:
        row = UpstreamGroup(name=payload.name)
        db.add(row)
        db.flush()
    accounts = [db.get(UpstreamAccount, account_id) for account_id in set(payload.account_ids)]
    if any(account is None for account in accounts):
        raise HTTPException(404, 'Upstream account not found')
    row.max_concurrency = payload.max_concurrency
    row.enabled = payload.enabled
    selected = {account.id for account in accounts}
    existing = db.scalars(select(GroupAccount).where(GroupAccount.group_id == row.id)).all()
    for member in existing:
        if member.account_id not in selected:
            routed = db.scalar(select(ModelRoute).join(ModelMapping).where(
                ModelMapping.group_id == row.id, ModelRoute.account_id == member.account_id))
            if routed:
                raise HTTPException(409, 'Remove model routes before removing this account')
            db.delete(member)
    current = {member.account_id for member in existing}
    for account_id in selected - current:
        db.add(GroupAccount(group_id=row.id, account_id=account_id))
    db.commit()
    return {'id': row.id}


@router.get('/mappings')
def mappings(_: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[dict]:
    result = []
    for row in db.scalars(select(ModelMapping).order_by(ModelMapping.id)):
        price = db.scalar(select(PriceVersion).where(PriceVersion.model_mapping_id == row.id).order_by(
            PriceVersion.id.desc(),
        ))
        result.append({'id': row.id, 'public_name': row.public_name,
                       'group_id': row.group_id,
                       'upstream_account_id': row.upstream_account_id,
                       'upstream_model': row.upstream_model, 'enabled': row.enabled,
                       'max_concurrency': row.max_concurrency,
                       'routes': [{'account_id': route.account_id, 'upstream_model': route.upstream_model}
                                  for route in db.scalars(select(ModelRoute).where(ModelRoute.model_mapping_id == row.id)
                                                          .order_by(ModelRoute.id))],
                       'revision': row.revision,
                       'price': str(price.amount) if price else None,
                       'extra_amount': str(price.extra_amount) if price else '0.0000',
                       'billing_mode': price.billing_mode if price else None})
    return result


@router.post('/mappings')
def upsert_mapping(payload: MappingUpsert, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    group = db.get(UpstreamGroup, payload.group_id) if payload.group_id else default_group(db)
    if group is None:
        raise HTTPException(404, 'Group not found')
    routes = payload.routes or ([RouteInput(account_id=payload.upstream_account_id,
                                           upstream_model=payload.upstream_model)]
                                if payload.upstream_account_id and payload.upstream_model else [])
    if not routes or len({route.account_id for route in routes}) != len(routes):
        raise HTTPException(422, 'Provide distinct upstream routes')
    members = set(db.scalars(select(GroupAccount.account_id).where(GroupAccount.group_id == group.id)))
    if any(route.account_id not in members for route in routes):
        raise HTTPException(422, 'Every route must belong to the group')
    accounts = [db.get(UpstreamAccount, route.account_id) for route in routes]
    if any(account is None for account in accounts) or len({account.provider for account in accounts}) != 1:
        raise HTTPException(422, 'Routes must use the same provider')
    account = accounts[0]
    extra_amount = payload.extra_amount if payload.extra_amount is not None else (
        Decimal('0.1000') if account.provider == 'novelai' else Decimal('0')
    )
    if account.provider != 'novelai' and extra_amount:
        raise HTTPException(422, 'Per-generation surcharge is only supported for NovelAI models')
    row = db.scalar(select(ModelMapping).where(ModelMapping.group_id == group.id,
                                                ModelMapping.public_name == payload.public_name))
    if row is None:
        row = ModelMapping(public_name=payload.public_name, upstream_model=routes[0].upstream_model,
                           group_id=group.id, upstream_account_id=account.id, enabled=payload.enabled)
        db.add(row)
        db.flush()
    else:
        row.upstream_account_id = account.id
        row.enabled = payload.enabled
        row.revision += 1
    row.upstream_model = routes[0].upstream_model
    for old in db.scalars(select(ModelRoute).where(ModelRoute.model_mapping_id == row.id)).all():
        db.delete(old)
    db.flush()
    for route in routes:
        db.add(ModelRoute(model_mapping_id=row.id, account_id=route.account_id,
                          upstream_model=route.upstream_model))
    price = db.scalar(select(PriceVersion).where(PriceVersion.model_mapping_id == row.id).order_by(
        PriceVersion.id.desc(),
    ))
    billing_mode = 'anlas' if account.provider == 'novelai' else 'fixed'
    if price is None or price.amount != payload.price or price.extra_amount != extra_amount or price.billing_mode != billing_mode:
        db.add(PriceVersion(model_mapping_id=row.id, amount=payload.price,
                            extra_amount=extra_amount, billing_mode=billing_mode))
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
    job = db.get(GenerationJob, job_id)
    if payload.succeeded and job and job.anlas_cost is not None and payload.anlas_charged is None:
        raise HTTPException(422, 'Actual Anlas charge required')
    if payload.succeeded and job and job.status == JobStatus.UNCERTAIN:
        try:
            store_remote_image(job.id, payload.image_url, get_settings().upstream_timeout_seconds)
        except UpstreamUncertain as exc:
            raise HTTPException(422, str(exc)) from exc
    result = {'data': [{'url': payload.image_url}],
              'anlas_charged': payload.anlas_charged} if payload.succeeded else None
    resolve_uncertain(db, job_id, result, payload.note)
    return {'ok': True}
