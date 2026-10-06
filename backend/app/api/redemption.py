import hashlib
import secrets
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import RedemptionCode, User, WalletLedger, utcnow
from ..security import decrypt_upstream_key, encrypt_upstream_key
from ..services import require_user_lock
from .csv_utils import beijing_time, csv_response
from .deps import admin_user, csrf_user

router = APIRouter(prefix='/api', tags=['redemption'])


class CodeCreate(BaseModel):
    amount: Decimal = Field(gt=Decimal('0.1'), max_digits=14, decimal_places=4)
    count: int = Field(default=1, ge=1, le=100)


class CodeRedeem(BaseModel):
    code: str = Field(min_length=1, max_length=80)


@router.get('/admin/redemption-codes')
def list_codes(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
               _: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(RedemptionCode).where(RedemptionCode.deleted_at.is_(None))
                      .order_by(RedemptionCode.id.desc()).offset(offset).limit(limit)).all()
    return [{'id': row.id, 'prefix': row.prefix, 'amount': str(row.amount),
             'can_copy': bool(row.encrypted_code),
             'created_at': row.created_at, 'redeemed_by': row.redeemed_by,
             'redeemed_at': row.redeemed_at} for row in rows]


@router.post('/admin/redemption-codes')
def create_codes(payload: CodeCreate, admin: User = Depends(admin_user),
                 db: Session = Depends(get_db)) -> dict:
    codes = []
    for _ in range(payload.count):
        code = 'NVP-' + secrets.token_hex(12).upper()
        row = RedemptionCode(code_hash=hashlib.sha256(code.encode()).hexdigest(),
                             encrypted_code=encrypt_upstream_key(code), prefix=code[:12],
                             amount=payload.amount, created_by=admin.id)
        db.add(row)
        codes.append(code)
    db.commit()
    return {'codes': codes}


@router.get('/admin/redemption-codes/{code_id}/secret')
def code_secret(code_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(RedemptionCode, code_id)
    if row is None or row.deleted_at:
        raise HTTPException(404, 'Code not found')
    if not row.encrypted_code:
        raise HTTPException(404, 'Legacy code cannot be recovered; generate a new code')
    return {'code': decrypt_upstream_key(row.encrypted_code)}


@router.get('/admin/redemption-codes/export')
def export_codes(ids: list[int] | None = Query(default=None),
                 _: User = Depends(admin_user), db: Session = Depends(get_db)):
    query = select(RedemptionCode).where(RedemptionCode.deleted_at.is_(None))
    if ids is not None:
        query = query.where(RedemptionCode.id.in_(ids))
    result = db.scalars(query.order_by(RedemptionCode.id.desc()).execution_options(yield_per=500))
    rows = ((row.id, decrypt_upstream_key(row.encrypted_code) if row.encrypted_code else '',
             row.prefix, row.amount, '已使用' if row.redeemed_at else '未使用',
             row.redeemed_by or '', beijing_time(row.created_at), beijing_time(row.redeemed_at))
            for row in result)
    return csv_response('redemption-codes.csv',
        ['编号', '兑换码', '前缀', '面额', '状态', '兑换用户 ID',
         '创建时间 (北京时间)', '兑换时间 (北京时间)'], rows)


@router.delete('/admin/redemption-codes/{code_id}')
def delete_code(code_id: int, _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(RedemptionCode, code_id)
    if row is None or row.deleted_at:
        raise HTTPException(404, 'Code not found')
    row.deleted_at = utcnow()
    db.commit()
    return {'ok': True}


@router.post('/redemption-codes/redeem')
def redeem_code(payload: CodeRedeem, user: User = Depends(csrf_user),
                db: Session = Depends(get_db)) -> dict:
    digest = hashlib.sha256(payload.code.strip().upper().encode()).hexdigest()
    db.commit()
    with db.begin():
        owner = require_user_lock(db, user.id)
        row = db.scalar(select(RedemptionCode).where(RedemptionCode.code_hash == digest))
        if row is None or row.deleted_at or row.redeemed_at:
            raise HTTPException(409, 'Code is invalid or already used')
        claimed = db.execute(update(RedemptionCode).where(
            RedemptionCode.id == row.id, RedemptionCode.deleted_at.is_(None),
            RedemptionCode.redeemed_at.is_(None)).values(
                redeemed_by=owner.id, redeemed_at=utcnow()))
        if claimed.rowcount != 1:
            raise HTTPException(409, 'Code is invalid or already used')
        owner.balance += row.amount
        db.add(WalletLedger(user_id=owner.id, amount=row.amount,
                            kind='redemption', reference=f'redemption:{row.id}'))
        amount = row.amount
        balance = owner.balance
    return {'amount': str(amount), 'balance': str(balance)}
