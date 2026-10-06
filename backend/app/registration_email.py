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


LEGACY_TEMPLATE = '''<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#18212b">
  <h2>邮箱注册验证</h2>
  <p>您好，您的注册验证码是：</p>
  <p style="font-size:32px;font-weight:700;letter-spacing:6px">{{code}}</p>
  <p>验证码将在 {{expires_minutes}} 分钟后失效（{{expires_at}}）。请勿转发给他人。</p>
</div>'''
DEFAULT_TEMPLATE = '''<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:#11121b;font-family:Arial,'Microsoft YaHei',sans-serif;color:#252536;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#11121b;border-collapse:collapse;">
    <tr><td align="center" style="padding:36px 14px;">
      <table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:560px;border-collapse:separate;border-spacing:0;">
        <tr><td style="padding:0 4px 18px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr>
            <td width="42" style="width:42px;vertical-align:middle;"><div style="width:36px;height:36px;line-height:36px;text-align:center;border-radius:8px;background-color:#c0b3ff;color:#252037;font-size:21px;font-weight:800;">Y</div></td>
            <td style="vertical-align:middle;color:#f6f3ff;font-size:18px;font-weight:800;">YunZhanCloud</td>
            <td align="right" style="vertical-align:middle;color:#aaa5c2;font-size:10px;font-weight:700;white-space:nowrap;">SECURE ACCESS</td>
          </tr></table>
        </td></tr>
        <tr><td style="background-color:#ffffff;border-radius:8px 8px 0 0;padding:0;overflow:hidden;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr>
            <td width="72%" height="4" style="background-color:#ad9cf4;font-size:0;line-height:0;">&nbsp;</td>
            <td height="4" style="background-color:#62cdbb;font-size:0;line-height:0;">&nbsp;</td>
          </tr></table>
        </td></tr>
        <tr><td style="background-color:#ffffff;padding:38px 24px 12px;">
          <p style="margin:0 0 12px;color:#6556ac;font-size:11px;font-weight:800;">ACCOUNT VERIFICATION</p>
          <h1 style="margin:0 0 14px;color:#252536;font-size:27px;line-height:1.3;font-weight:800;">验证你的邮箱</h1>
          <p style="margin:0;color:#6d6b7b;font-size:14px;line-height:1.8;">欢迎加入 YunZhanCloud。请使用下面的验证码完成账户注册。</p>
        </td></tr>
        <tr><td style="background-color:#ffffff;padding:16px 24px 22px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#242332;border-collapse:separate;border-spacing:0;border-radius:8px;"><tr>
            <td style="padding:22px 16px 24px;text-align:center;border-left:4px solid #ad9cf4;">
              <p style="margin:0 0 12px;color:#bcb6d5;font-size:10px;font-weight:700;">YOUR VERIFICATION CODE</p>
              <p style="margin:0;color:#e0d9ff;font-size:28px;line-height:1.2;font-weight:800;letter-spacing:5px;white-space:nowrap;">{{code}}</p>
            </td>
          </tr></table>
        </td></tr>
        <tr><td style="background-color:#ffffff;padding:0 24px 35px;">
          <p style="margin:0 0 8px;color:#252536;font-size:13px;line-height:1.7;font-weight:700;">验证码 {{expires_minutes}} 分钟内有效</p>
          <p style="margin:0;color:#777584;font-size:12px;line-height:1.8;">失效时间：{{expires_at}}<br>如果你没有请求注册，请忽略这封邮件。请勿向他人透露验证码。</p>
        </td></tr>
        <tr><td style="background-color:#eceaf4;border-radius:0 0 8px 8px;padding:17px 24px;color:#777184;font-size:11px;line-height:1.6;">
          此邮件由 YunZhanCloud 自动发送，请勿直接回复。
        </td></tr>
        <tr><td align="center" style="padding:20px 8px 0;color:#79768b;font-size:10px;">YunZhanCloud &nbsp; / &nbsp; CREATE BEYOND LIMITS</td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>'''
RESERVED_VARS = {'code', 'email', 'expires_minutes', 'expires_at'}
PLACEHOLDER = re.compile(r'\{\{\s*([a-zA-Z][a-zA-Z0-9_]{0,49})\s*\}\}')


def registration_settings(db: Session) -> RegistrationSettings:
    row = db.get(RegistrationSettings, 1)
    if row is None:
        row = RegistrationSettings(id=1, enabled=get_business_config().registration.enabled,
                                   html_template=DEFAULT_TEMPLATE)
        db.add(row)
        db.flush()
    elif row.html_template.replace('\r\n', '\n').strip() == LEGACY_TEMPLATE:
        row.html_template = DEFAULT_TEMPLATE
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
    message.set_content('YunZhanCloud 注册验证码：' + code + f'，有效期 {row.code_expiry_minutes} 分钟。')
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
