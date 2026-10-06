from decimal import Decimal
from datetime import timedelta
import uuid
import re
from urllib.parse import urlparse
import httpx

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..config import get_settings
from ..group_access import can_use_group
from ..models import ApiKey, GenerationJob, GroupAccount, GroupMember, JobStatus, ModelMapping, ModelRoute, PriceVersion, UpstreamAccount, UpstreamGroup, User, utcnow
from ..registration_email import DEFAULT_TEMPLATE, PLACEHOLDER, RESERVED_VARS, email_ready, registration_settings, send_email
from ..security import decrypt_upstream_key, encrypt_upstream_key, hash_password, new_api_key
from ..services import credit_wallet, resolve_uncertain
from ..upstream import UpstreamUncertain, store_remote_image
from .deps import admin_user
from .user import job_view, key_view


router = APIRouter(prefix='/api/admin', tags=['admin'])


def has_unsettled_jobs(db: Session, *filters) -> bool:
    return db.scalar(select(GenerationJob.id).where(
        GenerationJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.UNCERTAIN]),
        *filters).limit(1)) is not None


def default_group(db: Session) -> UpstreamGroup:
    group = db.scalar(select(UpstreamGroup).where(UpstreamGroup.is_private.is_(False),
        UpstreamGroup.deleted_at.is_(None)).order_by(UpstreamGroup.id))
    if group is None:
        if db.scalar(select(UpstreamGroup.id).where(UpstreamGroup.name == '默认分组')):
            raise HTTPException(409, 'Restore the default group first')
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
    enabled: bool = True


class UpstreamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, min_length=1)
    opus_free: bool | None = None
    max_concurrency: int | None = Field(default=None, ge=1, le=1000)
    enabled: bool | None = None


class GroupUpsert(BaseModel):
    id: int | None = None
    name: str = Field(min_length=1, max_length=80)
    max_concurrency: int = Field(default=10, ge=1, le=1000)
    account_ids: list[int] = Field(default_factory=list)
    enabled: bool = True
    is_private: bool = False
    member_ids: list[int] = Field(default_factory=list)


class RouteInput(BaseModel):
    account_id: int
    upstream_model: str = Field(min_length=1, max_length=150)


class MappingUpsert(BaseModel):
    id: int | None = None
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


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    max_concurrency: int = Field(default=2, ge=1, le=100)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    email: EmailStr | None = None
    max_concurrency: int | None = Field(default=None, ge=1, le=100)
    is_active: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=12, max_length=200)


class KeyIssue(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    group_id: int | None = None


class Resolution(BaseModel):
    succeeded: bool
    image_url: str | None = None
    anlas_charged: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)


class RegistrationSettingsInput(BaseModel):
    enabled: bool
    smtp_host: str = Field(default='', max_length=255)
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_security: str = Field(default='ssl', pattern='^(ssl|starttls)$')
    smtp_username: str = Field(default='', max_length=320)
    smtp_password: str | None = None
    sender_email: str = Field(default='', max_length=320)
    subject: str = Field(default='邮箱注册验证码', min_length=1, max_length=200)
    html_template: str = Field(default=DEFAULT_TEMPLATE, min_length=1, max_length=30000)
    template_vars: dict[str, str] = Field(default_factory=dict)
    code_expiry_minutes: int = Field(default=15, ge=1, le=60)


def registration_view(row) -> dict:
    return {'enabled': row.enabled, 'smtp_host': row.smtp_host, 'smtp_port': row.smtp_port,
            'smtp_security': row.smtp_security, 'smtp_username': row.smtp_username,
            'smtp_password_configured': bool(row.smtp_password_encrypted),
            'sender_email': row.sender_email, 'subject': row.subject,
            'html_template': row.html_template, 'template_vars': row.template_vars or {},
            'code_expiry_minutes': row.code_expiry_minutes, 'email_configured': email_ready(row)}


@router.get('/registration-settings')
def get_registration_settings(_: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    return registration_view(registration_settings(db))


@router.put('/registration-settings')
def save_registration_settings(payload: RegistrationSettingsInput, _: User = Depends(admin_user),
                               db: Session = Depends(get_db)) -> dict:
    if '{{code}}' not in payload.html_template and not any(
        match.group(1) == 'code' for match in PLACEHOLDER.finditer(payload.html_template)
    ):
        raise HTTPException(422, 'HTML template must contain {{code}}')
    if len(payload.template_vars) > 30 or any(
        key in RESERVED_VARS or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{0,49}', key) or len(value) > 500
        for key, value in payload.template_vars.items()
    ):
        raise HTTPException(422, 'Invalid custom template variables')
    unknown = {match.group(1) for match in PLACEHOLDER.finditer(payload.html_template)} - RESERVED_VARS - payload.template_vars.keys()
    if unknown:
        raise HTTPException(422, f'Undefined template variables: {", ".join(sorted(unknown))}')
    if payload.sender_email:
        try:
            TypeAdapter(EmailStr).validate_python(payload.sender_email)
        except ValidationError:
            raise HTTPException(422, 'Invalid sender email')
    row = registration_settings(db)
    row.enabled = payload.enabled
    row.smtp_host = payload.smtp_host.strip()
    row.smtp_port = payload.smtp_port
    row.smtp_security = payload.smtp_security
    row.smtp_username = payload.smtp_username.strip()
    if payload.smtp_password:
        row.smtp_password_encrypted = encrypt_upstream_key(payload.smtp_password)
    row.sender_email = payload.sender_email.strip()
    row.subject = payload.subject.strip()
    row.html_template = payload.html_template
    row.template_vars = payload.template_vars
    row.code_expiry_minutes = payload.code_expiry_minutes
    db.commit()
    return registration_view(row)


@router.post('/registration-settings/test')
def test_registration_email(recipient: EmailStr, _: User = Depends(admin_user),
                            db: Session = Depends(get_db)) -> dict:
    row = registration_settings(db)
    if not email_ready(row):
        raise HTTPException(422, 'SMTP settings are incomplete')
    try:
        send_email(row, str(recipient), '123456', utcnow() + timedelta(minutes=row.code_expiry_minutes))
    except Exception:
        raise HTTPException(502, 'Test email could not be sent; check SMTP settings')
    return {'ok': True}


@router.get('/users')
def users(include_deleted: bool = False, search: str | None = None,
          offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
          _: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[dict]:
    query = select(User)
    if not include_deleted:
        query = query.where(User.deleted_at.is_(None))
    if search and search.strip():
        term = f'%{search.strip()}%'
        query = query.where(or_(User.display_name.ilike(term), User.email.ilike(term)))
    return [{'id': u.id, 'name': u.display_name, 'email': u.email,
             'role': 'admin' if u.is_admin else 'user', 'is_admin': u.is_admin,
             'balance': str(u.balance), 'reserved': str(u.reserved),
             'max_concurrency': u.max_concurrency, 'is_active': u.is_active,
             'deleted_at': u.deleted_at}
            for u in db.scalars(query.order_by(User.id.desc()).offset(offset).limit(limit))]


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
        if payload.email is not None:
            email = payload.email.strip().lower()
            duplicate = db.scalar(select(User.id).where(User.email == email, User.id != row.id))
            if duplicate:
                raise HTTPException(409, 'Email already exists')
            row.email = email
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


@router.post('/users/{user_id}/reset-password')
def reset_user_password(user_id: int, payload: PasswordReset, _: User = Depends(admin_user),
                        db: Session = Depends(get_db)) -> dict:
    row = db.get(User, user_id)
    if row is None or row.deleted_at:
        raise HTTPException(404, 'User not found')
    row.password_hash = hash_password(payload.password)
    row.session_version += 1
    db.commit()
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
    if not can_use_group(db, group, row.id):
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
    reference = f'admin:{uuid.uuid4().hex}'
    credit_wallet(db, payload.user_id, payload.amount, reference, 'admin_credit')
    return {'ok': True, 'reference': reference}


@router.get('/upstreams')
def upstreams(include_deleted: bool = False, _: User = Depends(admin_user),
              db: Session = Depends(get_db)) -> list[dict]:
    query = select(UpstreamAccount)
    if not include_deleted:
        query = query.where(UpstreamAccount.deleted_at.is_(None))
    return [{'id': row.id, 'name': row.name, 'base_url': row.base_url,
             'provider': row.provider, 'opus_free': row.opus_free, 'enabled': row.enabled,
             'max_concurrency': row.max_concurrency, 'deleted_at': row.deleted_at}
            for row in db.scalars(query.order_by(UpstreamAccount.id))]


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
                              max_concurrency=payload.max_concurrency, enabled=payload.enabled)
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
    if account is None or account.deleted_at:
        raise HTTPException(404, 'Upstream not found')
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(422, 'Name required')
        if db.scalar(select(UpstreamAccount.id).where(
                UpstreamAccount.name == name, UpstreamAccount.id != account.id)):
            raise HTTPException(409, 'Upstream name exists')
        account.name = name
    if payload.base_url is not None:
        parsed = urlparse(payload.base_url)
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')):
            raise HTTPException(422, 'Upstream URL must use HTTPS')
        if parsed.username or parsed.password or not parsed.hostname or parsed.query or parsed.fragment:
            raise HTTPException(422, 'Invalid upstream URL')
        account.base_url = payload.base_url.rstrip('/')
    if payload.api_key is not None:
        account.encrypted_key = encrypt_upstream_key(payload.api_key)
    if payload.opus_free is not None:
        account.opus_free = payload.opus_free
    if payload.max_concurrency is not None:
        account.max_concurrency = payload.max_concurrency
    if payload.enabled is not None:
        account.enabled = payload.enabled
    db.commit()
    return {'ok': True}


@router.delete('/upstreams/{account_id}')
def delete_upstream(account_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    account = db.get(UpstreamAccount, account_id)
    if account is None or account.deleted_at:
        raise HTTPException(404, 'Upstream not found')
    if has_unsettled_jobs(db, GenerationJob.upstream_account_id == account_id):
        raise HTTPException(409, 'Resolve active jobs before deleting this account')
    routed = db.scalar(select(ModelRoute.id).join(ModelMapping).where(
        ModelRoute.account_id == account_id, ModelMapping.deleted_at.is_(None)).limit(1))
    if routed is not None:
        raise HTTPException(409, 'Remove this account from published models first')
    for member in db.scalars(select(GroupAccount).where(GroupAccount.account_id == account_id)).all():
        db.delete(member)
    account.enabled = False
    account.deleted_at = utcnow()
    db.commit()
    return {'ok': True}


@router.post('/upstreams/{account_id}/restore')
def restore_upstream(account_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    account = db.get(UpstreamAccount, account_id)
    if account is None or not account.deleted_at:
        raise HTTPException(404, 'Deleted upstream not found')
    account.deleted_at = None
    db.commit()
    return {'ok': True}


@router.get('/upstreams/{account_id}/models')
def upstream_models(account_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    account = db.get(UpstreamAccount, account_id)
    if account is None or account.deleted_at:
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
def groups(include_deleted: bool = False, _: User = Depends(admin_user),
           db: Session = Depends(get_db)) -> list[dict]:
    query = select(UpstreamGroup)
    if not include_deleted:
        query = query.where(UpstreamGroup.deleted_at.is_(None))
    return [{'id': row.id, 'name': row.name, 'max_concurrency': row.max_concurrency,
             'enabled': row.enabled, 'is_private': row.is_private, 'deleted_at': row.deleted_at,
             'account_ids': list(db.scalars(select(GroupAccount.account_id).where(
                 GroupAccount.group_id == row.id).order_by(GroupAccount.id))),
             'member_ids': list(db.scalars(select(GroupMember.user_id).where(
                 GroupMember.group_id == row.id).order_by(GroupMember.user_id)))}
            for row in db.scalars(query.order_by(UpstreamGroup.id))]


@router.get('/group-recipients')
def group_recipients(_: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[dict]:
    return [{'id': row.id, 'name': row.display_name, 'email': row.email,
             'is_admin': row.is_admin} for row in db.scalars(select(User).where(
                 User.is_active.is_(True), User.deleted_at.is_(None)).order_by(User.id))]


@router.post('/groups')
def save_group(payload: GroupUpsert, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    members = set(payload.member_ids) if payload.is_private else set()
    if payload.is_private and not members:
        raise HTTPException(422, 'Private group needs at least one member')
    valid_members = set(db.scalars(select(User.id).where(
        User.id.in_(members), User.is_active.is_(True), User.deleted_at.is_(None))))
    if members != valid_members:
        raise HTTPException(422, 'Group members must be active registered users')
    row = db.get(UpstreamGroup, payload.id) if payload.id else None
    if payload.id and row is None:
        raise HTTPException(404, 'Group not found')
    if row and row.deleted_at:
        raise HTTPException(409, 'Restore group before editing')
    duplicate = db.scalar(select(UpstreamGroup).where(UpstreamGroup.name == payload.name))
    if duplicate and duplicate.id != (row.id if row else None):
        raise HTTPException(409, 'Group name exists')
    if row is None:
        row = UpstreamGroup(name=payload.name)
        db.add(row)
        db.flush()
    accounts = [db.get(UpstreamAccount, account_id) for account_id in set(payload.account_ids)]
    if any(account is None or account.deleted_at for account in accounts):
        raise HTTPException(404, 'Upstream account not found')
    row.name = payload.name
    row.max_concurrency = payload.max_concurrency
    row.enabled = payload.enabled
    row.is_private = payload.is_private
    for member in db.scalars(select(GroupMember).where(GroupMember.group_id == row.id)).all():
        db.delete(member)
    db.flush()
    for user_id in members:
        db.add(GroupMember(group_id=row.id, user_id=user_id))
    selected = {account.id for account in accounts}
    existing = db.scalars(select(GroupAccount).where(GroupAccount.group_id == row.id)).all()
    for member in existing:
        if member.account_id not in selected:
            routed = db.scalar(select(ModelRoute).join(ModelMapping).where(
                ModelMapping.group_id == row.id, ModelMapping.deleted_at.is_(None),
                ModelRoute.account_id == member.account_id))
            if routed:
                raise HTTPException(409, 'Remove model routes before removing this account')
            db.delete(member)
    current = {member.account_id for member in existing}
    for account_id in selected - current:
        db.add(GroupAccount(group_id=row.id, account_id=account_id))
    db.commit()
    return {'id': row.id}


@router.delete('/groups/{group_id}')
def delete_group(group_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    group = db.get(UpstreamGroup, group_id)
    if group is None or group.deleted_at:
        raise HTTPException(404, 'Group not found')
    if has_unsettled_jobs(db, GenerationJob.group_id == group_id):
        raise HTTPException(409, 'Resolve active jobs before deleting this group')
    group.enabled = False
    group.deleted_at = utcnow()
    for key in db.scalars(select(ApiKey).where(ApiKey.group_id == group_id,
                                              ApiKey.revoked_at.is_(None))):
        key.revoked_at = utcnow()
    db.commit()
    return {'ok': True}


@router.post('/groups/{group_id}/restore')
def restore_group(group_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    group = db.get(UpstreamGroup, group_id)
    if group is None or not group.deleted_at:
        raise HTTPException(404, 'Deleted group not found')
    group.deleted_at = None
    db.commit()
    return {'ok': True}


@router.get('/mappings')
def mappings(include_deleted: bool = False, _: User = Depends(admin_user),
             db: Session = Depends(get_db)) -> list[dict]:
    query = select(ModelMapping)
    if not include_deleted:
        query = query.where(ModelMapping.deleted_at.is_(None))
    result = []
    for row in db.scalars(query.order_by(ModelMapping.id)):
        price = db.scalar(select(PriceVersion).where(PriceVersion.model_mapping_id == row.id).order_by(
            PriceVersion.id.desc(),
        ))
        result.append({'id': row.id, 'public_name': row.public_name,
                       'group_id': row.group_id,
                       'upstream_account_id': row.upstream_account_id,
                       'upstream_model': row.upstream_model, 'enabled': row.enabled,
                       'deleted_at': row.deleted_at,
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
    if group is None or group.deleted_at:
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
    if any(account is None or account.deleted_at for account in accounts) or len({account.provider for account in accounts}) != 1:
        raise HTTPException(422, 'Routes must use the same provider')
    account = accounts[0]
    extra_amount = payload.extra_amount if payload.extra_amount is not None else (
        Decimal('0.1000') if account.provider == 'novelai' else Decimal('0')
    )
    if account.provider != 'novelai' and extra_amount:
        raise HTTPException(422, 'Per-generation surcharge is only supported for NovelAI models')
    row = db.get(ModelMapping, payload.id) if payload.id else None
    if payload.id and row is None:
        raise HTTPException(404, 'Model not found')
    if row and row.deleted_at:
        raise HTTPException(409, 'Restore model before editing')
    duplicate = db.scalar(select(ModelMapping).where(ModelMapping.group_id == group.id,
                                                  ModelMapping.public_name == payload.public_name))
    if row is None and duplicate and not duplicate.deleted_at:
        row = duplicate
    if duplicate and duplicate.id != (row.id if row else None):
        if duplicate.deleted_at:
            raise HTTPException(409, 'Restore archived model with this name first')
        raise HTTPException(409, 'Model name exists in this group')
    if row is None:
        row = ModelMapping(public_name=payload.public_name, upstream_model=routes[0].upstream_model,
                           group_id=group.id, upstream_account_id=account.id, enabled=payload.enabled)
        db.add(row)
        db.flush()
    else:
        if has_unsettled_jobs(db, GenerationJob.model_mapping_id == row.id):
            raise HTTPException(409, 'Resolve active jobs before editing this model')
        row.group_id = group.id
        row.public_name = payload.public_name
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


@router.delete('/mappings/{mapping_id}')
def delete_mapping(mapping_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(ModelMapping, mapping_id)
    if row is None or row.deleted_at:
        raise HTTPException(404, 'Model not found')
    if has_unsettled_jobs(db, GenerationJob.model_mapping_id == mapping_id):
        raise HTTPException(409, 'Resolve active jobs before deleting this model')
    row.enabled = False
    row.deleted_at = utcnow()
    db.commit()
    return {'ok': True}


@router.post('/mappings/{mapping_id}/restore')
def restore_mapping(mapping_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(ModelMapping, mapping_id)
    if row is None or not row.deleted_at:
        raise HTTPException(404, 'Deleted model not found')
    group = db.get(UpstreamGroup, row.group_id)
    if group is None or group.deleted_at:
        raise HTTPException(409, 'Restore the group first')
    members = set(db.scalars(select(GroupAccount.account_id).where(GroupAccount.group_id == row.group_id)))
    routes = db.scalars(select(ModelRoute).where(ModelRoute.model_mapping_id == row.id)).all()
    if not routes or any(route.account_id not in members or
                         (account := db.get(UpstreamAccount, route.account_id)) is None or account.deleted_at
                         for route in routes):
        raise HTTPException(409, 'Restore route accounts and group membership first')
    row.deleted_at = None
    db.commit()
    return {'ok': True}


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


@router.delete('/uncertain/{job_id}')
def delete_uncertain(job_id: str, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    resolve_uncertain(db, job_id, None, 'Administrator removed unresolved job and released reservation')
    job = db.get(GenerationJob, job_id)
    job.hidden_at = utcnow()
    db.commit()
    return {'ok': True}
