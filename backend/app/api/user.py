from datetime import date, datetime, time, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..group_access import can_use_group
from ..models import ApiKey, GenerationJob, ModelMapping, PriceVersion, UpstreamAccount, UpstreamGroup, UsageRecord, User, WalletLedger, utcnow
from ..security import decrypt_upstream_key, encrypt_upstream_key, new_api_key
from ..upstream import IMAGE_DIR
from .deps import csrf_user, current_user


router = APIRouter(prefix='/api', tags=['user'])


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    group_id: int | None = None


def key_view(key: ApiKey) -> dict:
    return {'id': key.id, 'name': key.name, 'prefix': key.prefix, 'group_id': key.group_id,
            'can_copy': bool(key.encrypted_key),
            'created_at': key.created_at, 'revoked_at': key.revoked_at}


def job_view(job: GenerationJob) -> dict:
    return {'id': job.id, 'model': job.public_model, 'prompt': job.prompt,
            'size': job.size, 'parameters': job.parameters or {}, 'anlas_cost': job.anlas_cost,
            'status': job.status, 'amount': '0.0000' if job.status == 'failed' else str(job.reserved_amount),
            'result': {'data': [{'url': f'/api/jobs/{job.id}/image'}]} if job.status == 'succeeded' and image_path(job.id) else None,
            'error': job.error, 'created_at': job.created_at,
            'finished_at': job.finished_at}


def image_path(job_id: str):
    return next((path for suffix in ('.png', '.jpg')
                 if (path := IMAGE_DIR / f'{job_id}{suffix}').is_file()), None)


@router.get('/keys')
def list_keys(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [key_view(k) for k in db.scalars(select(ApiKey).where(
        ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None),
    ).order_by(ApiKey.id.desc()))]


@router.post('/keys')
def create_key(payload: KeyCreate, user: User = Depends(csrf_user), db: Session = Depends(get_db)) -> dict:
    group = db.get(UpstreamGroup, payload.group_id) if payload.group_id else db.scalar(select(
        UpstreamGroup).where(UpstreamGroup.is_private.is_(False), UpstreamGroup.enabled.is_(True))
        .order_by(UpstreamGroup.id))
    if group is None and payload.group_id is None:
        group = UpstreamGroup(name='默认分组')
        db.add(group)
        db.flush()
    if not can_use_group(db, group, user.id):
        raise HTTPException(404, 'Group unavailable')
    raw, prefix, key_hash = new_api_key()
    key = ApiKey(user_id=user.id, group_id=group.id, name=payload.name, prefix=prefix, key_hash=key_hash,
                 encrypted_key=encrypt_upstream_key(raw))
    db.add(key)
    db.commit()
    db.refresh(key)
    return {**key_view(key), 'key': raw}


@router.get('/keys/{key_id}/secret')
def copy_key(key_id: int, user: User = Depends(csrf_user), db: Session = Depends(get_db)) -> dict:
    key = db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id,
                                         ApiKey.revoked_at.is_(None)))
    if key is None or not key.encrypted_key:
        raise HTTPException(404, 'Key cannot be copied; create a new key')
    return {'key': decrypt_upstream_key(key.encrypted_key)}


@router.delete('/keys/{key_id}')
def revoke_key(key_id: int, user: User = Depends(csrf_user), db: Session = Depends(get_db)) -> dict:
    key = db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id))
    if key is None:
        raise HTTPException(404, 'Key not found')
    key.revoked_at = utcnow()
    db.commit()
    return {'ok': True}


@router.get('/groups')
def available_groups(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [{'id': group.id, 'name': group.name} for group in db.scalars(select(UpstreamGroup).where(
        UpstreamGroup.enabled.is_(True)).order_by(UpstreamGroup.id))
        if can_use_group(db, group, user.id)]


@router.get('/models')
def list_models(user: User = Depends(current_user), group_id: int | None = None,
                db: Session = Depends(get_db)) -> list[dict]:
    mappings = db.scalars(select(ModelMapping).where(ModelMapping.enabled.is_(True)).order_by(
        ModelMapping.public_name,
    )).all()
    result = []
    for mapping in mappings:
        if group_id is not None and mapping.group_id != group_id:
            continue
        if not can_use_group(db, db.get(UpstreamGroup, mapping.group_id), user.id):
            continue
        price = db.scalar(select(PriceVersion).where(
            PriceVersion.model_mapping_id == mapping.id,
        ).order_by(PriceVersion.id.desc()))
        if price:
            account = db.get(UpstreamAccount, mapping.upstream_account_id)
            result.append({'name': mapping.public_name, 'group_id': mapping.group_id,
                           'price': str(price.amount),
                           'extra_amount': str(price.extra_amount),
                           'currency': price.currency, 'billing_mode': price.billing_mode,
                           'supports_smea': bool(account and account.provider == 'novelai' and
                                                 not mapping.upstream_model.startswith(('nai-diffusion-4', 'nai-diffusion-5'))),
                           })
    return result


@router.get('/jobs')
def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    jobs = db.scalars(select(GenerationJob).where(
        GenerationJob.user_id == user.id, GenerationJob.hidden_at.is_(None),
    ).order_by(
        GenerationJob.created_at.desc(), GenerationJob.id.desc(),
    ).limit(100)).all()
    return [job_view(job) for job in jobs]


@router.get('/usage')
def list_usage(user: User = Depends(current_user), db: Session = Depends(get_db),
               user_id: int | None = None, status: str | None = None,
               model: str | None = None, search: str | None = None,
               date_from: date | None = None, date_to: date | None = None,
               offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)) -> dict:
    query = select(GenerationJob, User).join(User, GenerationJob.user_id == User.id).where(
        GenerationJob.hidden_at.is_(None))
    if not user.is_admin:
        query = query.where(GenerationJob.user_id == user.id)
    elif user_id is not None:
        query = query.where(GenerationJob.user_id == user_id)
    if status:
        query = query.where(GenerationJob.status == status)
    if model:
        query = query.where(GenerationJob.public_model == model)
    if search:
        query = query.where(GenerationJob.id.contains(search.strip()))
    if date_from:
        query = query.where(GenerationJob.created_at >= beijing_start(date_from))
    if date_to:
        query = query.where(GenerationJob.created_at < beijing_start(date_to + timedelta(days=1)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
                      .offset(offset).limit(limit)).all()
    return {'total': total, 'items': [{**job_view(job), 'user_id': owner.id,
                                      'user_name': owner.display_name or owner.email}
                                     for job, owner in rows]}


@router.get('/usage/models')
def usage_models(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[str]:
    query = select(GenerationJob.public_model).where(GenerationJob.hidden_at.is_(None)).distinct().order_by(GenerationJob.public_model)
    if not user.is_admin:
        query = query.where(GenerationJob.user_id == user.id)
    return list(db.scalars(query))


class UsageDelete(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)


@router.post('/usage/delete')
def delete_usage(payload: UsageDelete, user: User = Depends(csrf_user),
                 db: Session = Depends(get_db)) -> dict:
    if not user.is_admin:
        raise HTTPException(403, 'Admin access required')
    ids = set(payload.ids)
    jobs = db.scalars(select(GenerationJob).where(
        GenerationJob.id.in_(ids), GenerationJob.hidden_at.is_(None),
    )).all()
    if len(jobs) != len(ids):
        raise HTTPException(404, 'Job not found')
    if any(job.status in ('queued', 'running', 'uncertain') for job in jobs):
        raise HTTPException(409, 'Active jobs cannot be deleted')
    for job in jobs:
        job.hidden_at = utcnow()
    db.commit()
    for job in jobs:
        for suffix in ('.png', '.jpg'):
            (IMAGE_DIR / f'{job.id}{suffix}').unlink(missing_ok=True)
    return {'deleted': len(jobs)}


@router.get('/jobs/{job_id}/image')
def job_image(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(GenerationJob, job_id)
    image = image_path(job_id)
    if job is None or job.user_id != user.id or job.status != 'succeeded' or image is None:
        raise HTTPException(404, 'Image not found')
    return FileResponse(image, media_type='image/png' if image.suffix == '.png' else 'image/jpeg', filename=image.name)


def beijing_start(day: date) -> datetime:
    return datetime.combine(day, time.min, timezone(timedelta(hours=8))).astimezone(timezone.utc)


@router.get('/billing')
def billing(user: User = Depends(current_user), db: Session = Depends(get_db),
            user_id: int | None = None, kind: str | None = None, model: str | None = None,
            search: str | None = None, date_from: date | None = None,
            date_to: date | None = None, offset: int = Query(0, ge=0),
            limit: int = Query(50, ge=1, le=100)) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, 'Invalid date range')
    owner_id = None if user.is_admin and user_id == 0 else (
        user_id if user.is_admin and user_id is not None else user.id)
    ledger_query = select(WalletLedger, User).join(User, WalletLedger.user_id == User.id).where(
        WalletLedger.hidden_at.is_(None))
    usage_query = select(UsageRecord, GenerationJob, User).join(
        GenerationJob, UsageRecord.job_id == GenerationJob.id).join(
        User, UsageRecord.user_id == User.id).where(
        UsageRecord.hidden_at.is_(None))
    if owner_id is not None:
        ledger_query = ledger_query.where(WalletLedger.user_id == owner_id)
        usage_query = usage_query.where(UsageRecord.user_id == owner_id)
    if kind:
        ledger_query = ledger_query.where(WalletLedger.kind == kind)
    if model:
        usage_query = usage_query.where(GenerationJob.public_model == model)
    if search:
        ledger_query = ledger_query.where(WalletLedger.reference.contains(search.strip()))
        usage_query = usage_query.where(UsageRecord.job_id.contains(search.strip()))
    if date_from:
        ledger_query = ledger_query.where(WalletLedger.created_at >= beijing_start(date_from))
        usage_query = usage_query.where(UsageRecord.created_at >= beijing_start(date_from))
    if date_to:
        end = beijing_start(date_to + timedelta(days=1))
        ledger_query = ledger_query.where(WalletLedger.created_at < end)
        usage_query = usage_query.where(UsageRecord.created_at < end)
    ledger_total = db.scalar(select(func.count()).select_from(ledger_query.subquery()))
    usage_total = db.scalar(select(func.count()).select_from(usage_query.subquery()))
    ledger = db.execute(ledger_query.order_by(WalletLedger.id.desc()).offset(offset).limit(limit)).all()
    usage = db.execute(usage_query.order_by(UsageRecord.id.desc()).offset(offset).limit(limit)).all()
    owner = db.get(User, owner_id) if owner_id is not None else None
    return {
        'balance': str(owner.balance) if owner else '0', 'reserved': str(owner.reserved) if owner else '0',
        'ledger_total': ledger_total, 'usage_total': usage_total,
        'ledger': [{'id': row.id, 'user_id': owner.id, 'user_name': owner.display_name or owner.email,
                    'kind': row.kind, 'amount': str(row.amount), 'reference': row.reference,
                    'created_at': row.created_at} for row, owner in ledger],
        'usage': [{'id': row.id, 'job_id': row.job_id, 'user_id': owner.id,
                   'user_name': owner.display_name or owner.email, 'model': job.public_model,
                   'amount': str(row.amount), 'price_version_id': row.price_version_id,
                   'created_at': row.created_at} for row, job, owner in usage],
    }


class BillingDelete(BaseModel):
    ledger_ids: list[int] = Field(default_factory=list, max_length=100)
    usage_ids: list[int] = Field(default_factory=list, max_length=100)


@router.post('/billing/delete')
def delete_billing(payload: BillingDelete, user: User = Depends(csrf_user),
                   db: Session = Depends(get_db)) -> dict:
    if not user.is_admin:
        raise HTTPException(403, 'Admin access required')
    if not payload.ledger_ids and not payload.usage_ids:
        raise HTTPException(422, 'Select records')
    ledgers = db.scalars(select(WalletLedger).where(WalletLedger.id.in_(set(payload.ledger_ids)),
                                                   WalletLedger.hidden_at.is_(None))).all()
    usages = db.scalars(select(UsageRecord).where(UsageRecord.id.in_(set(payload.usage_ids)),
                                                  UsageRecord.hidden_at.is_(None))).all()
    if len(ledgers) != len(set(payload.ledger_ids)) or len(usages) != len(set(payload.usage_ids)):
        raise HTTPException(404, 'Record not found')
    for row in [*ledgers, *usages]:
        row.hidden_at = utcnow()
    db.commit()
    return {'deleted': len(ledgers) + len(usages)}
