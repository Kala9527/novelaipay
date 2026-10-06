from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import GenerationJob, UsageRecord, User
from .csv_utils import beijing_time, csv_response
from .deps import current_user
from .user import beijing_start

router = APIRouter(prefix='/api', tags=['exports'])


@router.get('/usage/export')
def export_usage(user: User = Depends(current_user), db: Session = Depends(get_db),
                 user_id: int | None = None, status: str | None = None,
                 model: str | None = None, search: str | None = None,
                 date_from: date | None = None, date_to: date | None = None,
                 ids: list[str] | None = Query(default=None)):
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
    if ids is not None:
        query = query.where(GenerationJob.id.in_(ids))
    result = db.execute(query.order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
                        .execution_options(yield_per=500))
    rows = ((job.id, owner.id, owner.display_name or owner.email, job.public_model,
             job.status, job.size, job.reserved_amount if job.status != 'failed' else 0,
             job.anlas_cost, job.prompt, job.error or '', beijing_time(job.created_at),
             beijing_time(job.finished_at)) for job, owner in result)
    return csv_response('usage-records.csv',
        ['任务 ID', '用户 ID', '用户', '模型', '状态', '尺寸', '费用', 'Anlas',
         '提示词', '错误', '提交时间 (北京时间)', '完成时间 (北京时间)'], rows)


@router.get('/billing/consumption/export')
def export_consumption(user: User = Depends(current_user), db: Session = Depends(get_db),
                       user_id: int | None = None, model: str | None = None,
                       search: str | None = None, date_from: date | None = None,
                       date_to: date | None = None, ids: list[int] | None = Query(default=None)):
    owner_id = None if user.is_admin and user_id == 0 else (
        user_id if user.is_admin and user_id is not None else user.id)
    query = select(UsageRecord, GenerationJob, User).join(
        GenerationJob, UsageRecord.job_id == GenerationJob.id).join(
        User, UsageRecord.user_id == User.id).where(UsageRecord.hidden_at.is_(None))
    if owner_id is not None:
        query = query.where(UsageRecord.user_id == owner_id)
    if model:
        query = query.where(GenerationJob.public_model == model)
    if search:
        query = query.where(UsageRecord.job_id.contains(search.strip()))
    if date_from:
        query = query.where(UsageRecord.created_at >= beijing_start(date_from))
    if date_to:
        query = query.where(UsageRecord.created_at < beijing_start(date_to + timedelta(days=1)))
    if ids is not None:
        query = query.where(UsageRecord.id.in_(ids))
    result = db.execute(query.order_by(UsageRecord.id.desc()).execution_options(yield_per=500))
    rows = ((record.id, record.job_id, owner.id, owner.display_name or owner.email,
             job.public_model, record.amount, record.price_version_id,
             beijing_time(record.created_at)) for record, job, owner in result)
    return csv_response('consumption-records.csv',
        ['消费 ID', '任务 ID', '用户 ID', '用户', '模型', '金额', '价格版本 ID',
         '消费时间 (北京时间)'], rows)
