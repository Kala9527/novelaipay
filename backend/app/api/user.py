from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ApiKey, GenerationJob, ModelMapping, PriceVersion, UpstreamAccount, UsageRecord, User, WalletLedger, utcnow
from ..security import decrypt_upstream_key, encrypt_upstream_key, new_api_key
from ..upstream import IMAGE_DIR
from .deps import csrf_user, current_user


router = APIRouter(prefix='/api', tags=['user'])


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def key_view(key: ApiKey) -> dict:
    return {'id': key.id, 'name': key.name, 'prefix': key.prefix,
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
    raw, prefix, key_hash = new_api_key()
    key = ApiKey(user_id=user.id, name=payload.name, prefix=prefix, key_hash=key_hash,
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


@router.get('/models')
def list_models(_: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    mappings = db.scalars(select(ModelMapping).where(ModelMapping.enabled.is_(True)).order_by(
        ModelMapping.public_name,
    )).all()
    result = []
    for mapping in mappings:
        price = db.scalar(select(PriceVersion).where(
            PriceVersion.model_mapping_id == mapping.id,
        ).order_by(PriceVersion.id.desc()))
        if price:
            account = db.get(UpstreamAccount, mapping.upstream_account_id)
            result.append({'name': mapping.public_name, 'price': str(price.amount),
                           'extra_amount': str(price.extra_amount),
                           'currency': price.currency, 'billing_mode': price.billing_mode,
                           'supports_smea': bool(account and account.provider == 'novelai' and
                                                 not mapping.upstream_model.startswith(('nai-diffusion-4', 'nai-diffusion-5'))),
                           'max_concurrency': mapping.max_concurrency})
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


@router.get('/billing')
def billing(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    ledger = db.scalars(select(WalletLedger).where(WalletLedger.user_id == user.id).order_by(
        WalletLedger.id.desc(),
    ).limit(100)).all()
    usage = db.scalars(select(UsageRecord).where(UsageRecord.user_id == user.id).order_by(
        UsageRecord.id.desc(),
    ).limit(100)).all()
    return {
        'balance': str(user.balance), 'reserved': str(user.reserved),
        'ledger': [{'id': row.id, 'kind': row.kind, 'amount': str(row.amount),
                    'reference': row.reference, 'created_at': row.created_at} for row in ledger],
        'usage': [{'job_id': row.job_id, 'amount': str(row.amount),
                   'price_version_id': row.price_version_id, 'created_at': row.created_at} for row in usage],
    }
