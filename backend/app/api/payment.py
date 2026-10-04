import hashlib
import hmac
import json
import time
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..services import record_payment


router = APIRouter(prefix='/api/payments', tags=['payment'])


@router.post('/webhook')
async def webhook(
    request: Request,
    signature: str = Header(alias='X-Novelaipay-Signature'),
    timestamp: str = Header(alias='X-Novelaipay-Timestamp'),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ts = int(timestamp)
    except ValueError:
        raise HTTPException(401, 'Invalid timestamp') from None
    if abs(time.time() - ts) > 300:
        raise HTTPException(401, 'Expired timestamp')
    body = await request.body()
    expected = hmac.new(get_settings().payment_webhook_secret.encode(),
                        timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, 'Invalid signature')
    try:
        data = json.loads(body)
        provider = str(data['provider'])
        transaction_id = str(data['transaction_id'])
        user_id = int(data['user_id'])
        amount = Decimal(str(data['amount']))
        if not provider or not transaction_id or len(provider) > 50 or len(transaction_id) > 150:
            raise ValueError
    except (ValueError, KeyError, TypeError, InvalidOperation):
        raise HTTPException(422, 'Invalid payment payload') from None
    created = record_payment(db, provider, transaction_id, user_id, amount)
    return {'accepted': True, 'credited': created}
