import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    ApiKey, GenerationJob, JobStatus, ModelMapping, ModelRoute, PaymentOrder, PriceVersion,
    UpstreamAccount, UpstreamGroup, UsageRecord, User, WalletLedger, utcnow,
)
from .novelai import ImageParameters, estimate_anlas, store_image_inputs, validate_size


def require_user_lock(db: Session, user_id: int, allow_inactive: bool = False) -> User:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None or (not allow_inactive and (not user.is_active or user.deleted_at)):
        raise HTTPException(403, 'Account unavailable')
    return user


def submit_job(db: Session, api_key: ApiKey, model_name: str, prompt: str, size: str,
               idem: str, parameters: ImageParameters | None = None) -> GenerationJob:
    parameters = parameters or ImageParameters()
    request_hash = hashlib.sha256(json.dumps(
        {'model': model_name, 'prompt': prompt, 'size': size,
         'parameters': parameters.model_dump()}, sort_keys=True,
    ).encode()).hexdigest()
    db.commit()
    with db.begin():
        user = require_user_lock(db, api_key.user_id)
        existing = db.scalar(select(GenerationJob).where(
            GenerationJob.user_id == user.id, GenerationJob.idempotency_key == idem,
        ))
        if existing:
            if existing.group_id != api_key.group_id or existing.request_hash != request_hash:
                raise HTTPException(409, 'Idempotency key used with different request')
            return existing
        mapping = db.scalar(select(ModelMapping).where(
            ModelMapping.public_name == model_name, ModelMapping.group_id == api_key.group_id,
            ModelMapping.enabled.is_(True),
        ))
        if mapping is None:
            raise HTTPException(404, 'Model unavailable')
        group = db.get(UpstreamGroup, mapping.group_id)
        if group is None or not group.enabled:
            raise HTTPException(503, 'Group unavailable')
        routes = db.scalars(select(ModelRoute).where(ModelRoute.model_mapping_id == mapping.id)
                            .order_by(ModelRoute.id)).all()
        options = [(route, db.get(UpstreamAccount, route.account_id)) for route in routes]
        options = [(route, account) for route, account in options if account and account.enabled]
        if not options:
            raise HTTPException(503, 'Upstream unavailable')
        selected_route, account = options[0]
        price = db.scalar(select(PriceVersion).where(
            PriceVersion.model_mapping_id == mapping.id,
        ).order_by(PriceVersion.id.desc()))
        if price is None:
            raise HTTPException(503, 'Model has no price')
        anlas_cost = None
        amount = price.amount
        if account.provider == 'novelai':
            try:
                validate_size(size)
                anlas_cost = max(estimate_anlas(route.upstream_model, size, parameters,
                                                candidate.opus_free)
                                 for route, candidate in options)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            # Keep room for changes in NovelAI's unpublished price formula.
            amount = price.amount * anlas_cost * 2 + price.extra_amount
            try:
                stored_parameters = store_image_inputs(parameters)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
        else:
            stored_parameters = store_image_inputs(parameters)
        if user.balance - user.reserved < amount:
            raise HTTPException(402, 'Insufficient balance')
        user.reserved += amount
        job = GenerationJob(
            id=str(uuid.uuid4()), user_id=user.id, api_key_id=api_key.id,
            group_id=group.id,
            model_mapping_id=mapping.id, price_version_id=price.id,
            upstream_account_id=account.id, public_model=mapping.public_name,
            upstream_model=selected_route.upstream_model, mapping_revision=mapping.revision,
            prompt=prompt, size=size, parameters=stored_parameters, anlas_cost=anlas_cost,
            request_hash=request_hash, idempotency_key=idem, status=JobStatus.QUEUED,
            reserved_amount=amount,
        )
        db.add(job)
    return job


def credit_wallet(db: Session, user_id: int, amount: Decimal, reference: str, kind: str) -> None:
    if amount <= 0:
        raise HTTPException(422, 'Amount must be positive')
    db.commit()
    with db.begin():
        user = require_user_lock(db, user_id)
        if db.scalar(select(WalletLedger).where(WalletLedger.reference == reference)):
            raise HTTPException(409, 'Reference already credited')
        user.balance += amount
        db.add(WalletLedger(user_id=user_id, amount=amount, kind=kind, reference=reference))


def record_payment(db: Session, provider: str, transaction_id: str, user_id: int, amount: Decimal) -> bool:
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -4 or amount >= Decimal('10000000000'):
        raise HTTPException(422, 'Amount must be positive')
    db.commit()
    with db.begin():
        user = require_user_lock(db, user_id)
        previous = db.scalar(select(PaymentOrder).where(
            PaymentOrder.provider == provider, PaymentOrder.transaction_id == transaction_id,
        ))
        if previous:
            if previous.user_id != user_id or previous.amount != amount:
                raise HTTPException(409, 'Transaction payload mismatch')
            return False
        reference = 'payment:' + hashlib.sha256(f'{provider}:{transaction_id}'.encode()).hexdigest()
        user.balance += amount
        db.add(PaymentOrder(provider=provider, transaction_id=transaction_id, user_id=user_id, amount=amount))
        db.add(WalletLedger(user_id=user_id, amount=amount, kind='payment', reference=reference))
    return True


def claim_job(db: Session, lease_seconds: int, job_id: str | None = None) -> GenerationJob | None:
    with db.begin():
        query = select(GenerationJob).where(GenerationJob.status == JobStatus.QUEUED)
        if job_id is not None:
            query = query.where(GenerationJob.id == job_id)
        query = query.order_by(
            GenerationJob.created_at, GenerationJob.id,
        ).limit(20)
        if db.bind.dialect.name == 'postgresql':
            query = query.with_for_update(skip_locked=True)
        job = None
        for candidate in db.scalars(query):
            group = db.scalar(select(UpstreamGroup).where(
                UpstreamGroup.id == candidate.group_id).with_for_update())
            if group is None or not group.enabled:
                continue
            running = db.scalar(select(func.count()).select_from(GenerationJob).where(
                GenerationJob.group_id == group.id,
                GenerationJob.status == JobStatus.RUNNING))
            if running >= group.max_concurrency:
                continue
            if not select_available_route(db, candidate):
                continue
            job = candidate
            job.status = JobStatus.RUNNING
            job.lease_until = utcnow() + timedelta(seconds=lease_seconds)
            break
    return job


def select_available_route(db: Session, job: GenerationJob, excluded: set[int] | None = None) -> bool:
    routes = db.scalars(select(ModelRoute).where(ModelRoute.model_mapping_id == job.model_mapping_id)
                        .order_by(ModelRoute.account_id)).all()
    available = []
    for route in routes:
        if route.account_id in (excluded or set()):
            continue
        account = db.scalar(select(UpstreamAccount).where(
            UpstreamAccount.id == route.account_id).with_for_update())
        if account is None or not account.enabled:
            continue
        busy = db.scalar(select(func.count()).select_from(GenerationJob).where(
            GenerationJob.upstream_account_id == account.id,
            GenerationJob.status.in_([JobStatus.RUNNING, JobStatus.UNCERTAIN])))
        if busy >= account.max_concurrency:
            continue
        available.append((busy, route, account))
    if not available:
        return False
    mapping = db.get(ModelMapping, job.model_mapping_id)
    busy, route, account = min(available, key=lambda item: (
        item[0], item[1].account_id != mapping.upstream_account_id, item[1].account_id))
    if account.provider == 'novelai' and busy:
        job.billing_overlap = True
        for overlapping in db.scalars(select(GenerationJob).where(
                GenerationJob.upstream_account_id == account.id,
                GenerationJob.status == JobStatus.RUNNING)):
            overlapping.billing_overlap = True
    job.upstream_account_id = account.id
    job.upstream_model = route.upstream_model
    return True


def switch_job_account(db: Session, job_id: str, excluded: set[int]) -> bool:
    db.rollback()
    with db.begin():
        job = db.scalar(select(GenerationJob).where(GenerationJob.id == job_id).with_for_update())
        if job is None or job.status != JobStatus.RUNNING:
            return False
        return select_available_route(db, job, excluded)


def recover_expired(db: Session) -> int:
    with db.begin():
        query = select(GenerationJob).where(
            GenerationJob.status == JobStatus.RUNNING,
            GenerationJob.lease_until < utcnow(),
        )
        if db.bind.dialect.name == 'postgresql':
            query = query.with_for_update(skip_locked=True)
        jobs = db.scalars(query).all()
        for job in jobs:
            job.status = JobStatus.UNCERTAIN
            job.error = 'Worker lease expired; check upstream before settlement'
            job.lease_until = None
    return len(jobs)


def finish_job(db: Session, job_id: str, result: dict | None, error: str | None, uncertain: bool = False) -> None:
    with db.begin():
        job = db.scalar(select(GenerationJob).where(GenerationJob.id == job_id).with_for_update())
        if job is None or job.status != JobStatus.RUNNING:
            return
        user = require_user_lock(db, job.user_id, allow_inactive=True)
        job.lease_until = None
        if uncertain:
            job.status = JobStatus.UNCERTAIN
            job.error = error
            return
        if result is not None and job.billing_overlap:
            job.status = JobStatus.UNCERTAIN
            job.error = 'NovelAI account had overlapping jobs; verify each Anlas charge before settlement'
            return
        charged_amount = job.reserved_amount
        if result is not None and job.anlas_cost is not None:
            actual_anlas = result.get('anlas_charged')
            if not isinstance(actual_anlas, int) or actual_anlas < 0:
                job.status = JobStatus.UNCERTAIN
                job.error = 'NovelAI charge missing; reconcile manually'
                return
            price = db.get(PriceVersion, job.price_version_id)
            charged_amount = price.amount * actual_anlas + price.extra_amount
            if charged_amount > job.reserved_amount and user.balance - user.reserved + job.reserved_amount < charged_amount:
                job.status = JobStatus.UNCERTAIN
                job.error = 'NovelAI charge exceeds available balance; reconcile manually'
                return
        user.reserved -= job.reserved_amount
        job.finished_at = utcnow()
        if result is None:
            job.status = JobStatus.FAILED
            job.error = error or 'Upstream failed'
            return
        job.status = JobStatus.SUCCEEDED
        # Images are served from disk and never serialized into the job row.
        job.reserved_amount = charged_amount
        job.anlas_cost = result['anlas_charged'] if result is not None and job.anlas_cost is not None else job.anlas_cost
        user.balance -= charged_amount
        db.add(WalletLedger(
            user_id=user.id, amount=-charged_amount,
            kind='usage', reference=f'job:{job.id}',
        ))
        db.add(UsageRecord(
            user_id=user.id, job_id=job.id,
            price_version_id=job.price_version_id, amount=charged_amount,
        ))


def resolve_uncertain(db: Session, job_id: str, result: dict | None, error: str | None) -> None:
    db.commit()
    with db.begin():
        job = db.scalar(select(GenerationJob).where(GenerationJob.id == job_id).with_for_update())
        if job is None or job.status != JobStatus.UNCERTAIN:
            raise HTTPException(409, 'Job is not awaiting reconciliation')
        user = require_user_lock(db, job.user_id, allow_inactive=True)
        charged_amount = job.reserved_amount
        if result is not None and job.anlas_cost is not None:
            actual_anlas = result.get('anlas_charged')
            if not isinstance(actual_anlas, int) or actual_anlas < 0:
                raise HTTPException(422, 'Actual Anlas charge required')
            price = db.get(PriceVersion, job.price_version_id)
            charged_amount = price.amount * actual_anlas + price.extra_amount
            if user.balance - user.reserved + job.reserved_amount < charged_amount:
                raise HTTPException(402, 'Credit wallet before reconciling charge')
        user.reserved -= job.reserved_amount
        job.finished_at = utcnow()
        job.error = error
        if result is None:
            job.status = JobStatus.FAILED
        else:
            job.status = JobStatus.SUCCEEDED
            # Reconciliation updates billing metadata without persisting image data.
            job.reserved_amount = charged_amount
            if job.anlas_cost is not None:
                job.anlas_cost = result['anlas_charged']
            user.balance -= charged_amount
            db.add(WalletLedger(user_id=user.id, amount=-charged_amount,
                                kind='usage', reference=f'job:{job.id}'))
            db.add(UsageRecord(user_id=user.id, job_id=job.id,
                               price_version_id=job.price_version_id, amount=charged_amount))
