from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ApiKey, GenerationJob, ModelMapping, PriceVersion, UsageRecord, User, WalletLedger, utcnow
from ..security import new_api_key
from .deps import csrf_user, current_user


router = APIRouter(prefix='/api', tags=['user'])


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def key_view(key: ApiKey) -> dict:
    return {'id': key.id, 'name': key.name, 'prefix': key.prefix,
            'created_at': key.created_at, 'revoked_at': key.revoked_at}


def job_view(job: GenerationJob) -> dict:
    return {'id': job.id, 'model': job.public_model, 'prompt': job.prompt,
            'size': job.size, 'status': job.status, 'amount': str(job.reserved_amount),
            'result': job.result, 'error': job.error, 'created_at': job.created_at,
            'finished_at': job.finished_at}


@router.get('/keys')
def list_keys(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [key_view(k) for k in db.scalars(select(ApiKey).where(
        ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None),
    ).order_by(ApiKey.id.desc()))]


@router.post('/keys')
def create_key(payload: KeyCreate, user: User = Depends(csrf_user), db: Session = Depends(get_db)) -> dict:
    raw, prefix, key_hash = new_api_key()
    key = ApiKey(user_id=user.id, name=payload.name, prefix=prefix, key_hash=key_hash)
    db.add(key)
    db.commit()
    db.refresh(key)
    return {**key_view(key), 'key': raw}


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
            result.append({'name': mapping.public_name, 'price': str(price.amount),
                           'currency': price.currency, 'max_concurrency': mapping.max_concurrency})
    return result


@router.get('/jobs')
def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    jobs = db.scalars(select(GenerationJob).where(GenerationJob.user_id == user.id).order_by(
        GenerationJob.created_at.desc(), GenerationJob.id.desc(),
    ).limit(100)).all()
    return [job_view(job) for job in jobs]


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
