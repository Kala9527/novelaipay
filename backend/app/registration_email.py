import hashlib
import hmac
import html
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy.orm import Session

from .config import get_business_config, get_settings
from .models import RegistrationSettings
from .security import decrypt_upstream_key


DEFAULT_TEMPLATE = '''<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#18212b">
  <h2>邮箱注册验证</h2>
  <p>您好，您的注册验证码是：</p>
  <p style="font-size:32px;font-weight:700;letter-spacing:6px">{{code}}</p>
  <p>验证码将在 {{expires_minutes}} 分钟后失效（{{expires_at}}）。请勿转发给他人。</p>
</div>'''
RESERVED_VARS = {'code', 'email', 'expires_minutes', 'expires_at'}
PLACEHOLDER = re.compile(r'\{\{\s*([a-zA-Z][a-zA-Z0-9_]{0,49})\s*\}\}')


def registration_settings(db: Session) -> RegistrationSettings:
    row = db.get(RegistrationSettings, 1)
    if row is None:
        row = RegistrationSettings(id=1, enabled=get_business_config().registration.enabled,
                                   html_template=DEFAULT_TEMPLATE)
        db.add(row)
        db.flush()
    return row


def email_ready(row: RegistrationSettings) -> bool:
    return bool(row.smtp_host and row.smtp_username and row.smtp_password_encrypted and row.sender_email)


def code_digest(email: str, code: str) -> str:
    key = get_settings().app_secret_key.encode()
    return hmac.new(key, f'{email}:{code}'.encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    return f'{secrets.randbelow(1000000):06d}'


def render_template(row: RegistrationSettings, email: str, code: str,
                    expires_at: datetime) -> str:
    values = {**(row.template_vars or {}), 'code': code, 'email': email,
              'expires_minutes': str(row.code_expiry_minutes),
              'expires_at': expires_at.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M 北京时间')}
    return PLACEHOLDER.sub(lambda match: html.escape(str(values.get(match.group(1), match.group(0)))),
                           row.html_template)


def send_email(row: RegistrationSettings, recipient: str, code: str,
               expires_at: datetime) -> None:
    message = EmailMessage()
    message['From'] = row.sender_email
    message['To'] = recipient
    message['Subject'] = row.subject
    message.set_content('您的注册验证码是 ' + code + f'，有效期 {row.code_expiry_minutes} 分钟。')
    message.add_alternative(render_template(row, recipient, code, expires_at), subtype='html')
    password = decrypt_upstream_key(row.smtp_password_encrypted)
    context = ssl.create_default_context()
    if row.smtp_security == 'ssl':
        client = smtplib.SMTP_SSL(row.smtp_host, row.smtp_port, timeout=10, context=context)
    else:
        client = smtplib.SMTP(row.smtp_host, row.smtp_port, timeout=10)
    with client:
        if row.smtp_security == 'starttls':
            client.starttls(context=context)
        client.login(row.smtp_username, password)
        client.send_message(message)
