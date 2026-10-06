import hashlib
import csv
import hmac
import json
import io
import os
import tempfile
import time
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import httpx
from PIL import Image

from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

os.environ.update({
    'APP_SECRET_KEY': 'test-session-secret-with-enough-length',
    'UPSTREAM_KEY_ENCRYPTION_KEY': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
    'PAYMENT_WEBHOOK_SECRET': 'test-payment-secret',
    'DATABASE_URL': 'sqlite://',
    'COOKIE_SECURE': 'false',
    'CORS_ALLOWED_ORIGINS': 'http://127.0.0.1:8009,http://localhost:8009',
    'CONFIG_FILE': str(Path(__file__).resolve().parent / 'config.test.yaml'),
})

from fastapi.testclient import TestClient

from app import db
from app.bootstrap import main as bootstrap_admin
from app.config import AdminConfig, RegistrationConfig, get_business_config
from app.main import app
from app.models import Base, GenerationJob, GroupMember, JobStatus, ModelMapping, ModelRoute, PriceVersion, RedemptionCode, RegistrationCode, RegistrationSettings, UpstreamAccount, UpstreamGroup, UsageRecord, utcnow
from app.models import User
from app.security import verify_password
from app.services import claim_job, recover_expired
from app.worker import run_once
from app.api.tavern import normalize_request
from app.novelai import ImageParameters, generation_payload
from app.upstream import OpenAIImageAdapter
from app.security import encrypt_upstream_key
from app.registration_email import render_template
import base64


class FlowTest(unittest.TestCase):
    def setUp(self):
        db.engine.dispose()
        db.engine = create_engine('sqlite://', poolclass=StaticPool,
                                  connect_args={'check_same_thread': False})
        db.SessionLocal.configure(bind=db.engine)
        Base.metadata.create_all(db.engine)
        bootstrap_admin()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        db.engine.dispose()

    def login(self, email, password):
        response = self.client.post('/api/auth/login', json={'email': email, 'password': password})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def admin_post(self, path, payload):
        return self.client.post(path, json=payload, headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']})

    def admin_patch(self, path, payload):
        return self.client.patch(path, json=payload, headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']})

    def register(self, name, email, password):
        with db.SessionLocal.begin() as session:
            row = session.get(RegistrationSettings, 1)
            if row is None:
                row = RegistrationSettings(id=1, enabled=True, html_template='{{code}}')
                session.add(row)
            row.smtp_host = 'smtp.example.com'
            row.smtp_username = 'sender@example.com'
            row.smtp_password_encrypted = encrypt_upstream_key('test-password')
            row.sender_email = 'sender@example.com'
        with patch('app.api.auth.send_email'), patch('app.api.auth.new_code', return_value='123456'):
            sent = self.client.post('/api/auth/registration-code', json={'email': email})
        self.assertEqual(sent.status_code, 200, sent.text)
        return self.client.post('/api/auth/register', json={
            'name': name, 'email': email, 'password': password, 'code': '123456',
        })

    def test_registration_email_settings_and_verification(self):
        self.login('admin@example.com', 'long-test-password')
        headers = {'X-CSRF-Token': self.client.cookies['nvp_csrf']}
        settings = self.client.get('/api/admin/registration-settings', headers=headers).json()
        payload = {**settings, 'smtp_host': 'smtp.qq.com', 'smtp_username': 'sender@qq.com',
                   'smtp_password': 'device-code', 'sender_email': 'sender@qq.com',
                   'html_template': '<p>{{code}} {{site_name}} {{expires_at}}</p>',
                   'template_vars': {'site_name': '<NovelAI>'}, 'code_expiry_minutes': 15}
        self.assertEqual(self.client.put('/api/admin/registration-settings', json={
            **payload, 'html_template': '<p>missing code</p>',
        }, headers=headers).status_code, 422)
        saved = self.client.put('/api/admin/registration-settings', json=payload, headers=headers)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(saved.json()['email_configured'])
        self.assertNotIn('device-code', str(saved.json()))
        with patch('app.api.admin.send_email') as sender:
            test_mail = self.admin_post('/api/admin/registration-settings/test?recipient=admin@example.com', {})
            self.assertEqual(test_mail.status_code, 200, test_mail.text)
            sender.assert_called_once()
        with db.SessionLocal() as session:
            row = session.get(RegistrationSettings, 1)
            self.assertNotIn('device-code', row.smtp_password_encrypted)
            self.assertIn('&lt;NovelAI&gt;', render_template(row, 'new@example.com', '123456', utcnow()))
        self.client.cookies.clear()
        with patch('app.api.auth.send_email') as sender, patch('app.api.auth.new_code', return_value='123456'):
            sent = self.client.post('/api/auth/registration-code', json={'email': 'new@example.com'})
            self.assertEqual(sent.status_code, 200, sent.text)
            self.assertEqual(sender.call_count, 1)
        self.assertEqual(self.client.post('/api/auth/registration-code', json={
            'email': 'new@example.com',
        }).status_code, 429)
        with db.SessionLocal.begin() as session:
            issued = session.get(RegistrationCode, 'new@example.com')
            issued.expires_at = utcnow() - timedelta(seconds=1)
        registration = {'name': 'New User', 'email': 'new@example.com',
                        'password': 'strong-user-password', 'code': '000000'}
        self.assertEqual(self.client.post('/api/auth/register', json=registration).status_code, 400)
        with db.SessionLocal.begin() as session:
            issued = session.get(RegistrationCode, 'new@example.com')
            issued.expires_at = utcnow() + timedelta(minutes=15)
        self.assertEqual(self.client.post('/api/auth/register', json={
            **registration, 'code': '123456',
        }).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/register', json={
            **registration, 'code': '123456',
        }).status_code, 409)
        with db.SessionLocal() as session:
            self.assertIsNone(session.get(RegistrationCode, 'new@example.com'))

    def test_redemption_codes_and_generated_credit_reference(self):
        self.login('admin@example.com', 'long-test-password')
        created = self.admin_post('/api/admin/users', {
            'name': 'Redeemer', 'email': 'redeemer@example.com', 'password': 'user-password-123',
        })
        self.assertEqual(created.status_code, 200, created.text)
        user_id = created.json()['id']
        credit = self.admin_post('/api/admin/credit', {'user_id': user_id, 'amount': '2'})
        self.assertEqual(credit.status_code, 200, credit.text)
        self.assertTrue(credit.json()['reference'].startswith('admin:'))
        self.assertNotEqual(credit.json()['reference'], self.admin_post(
            '/api/admin/credit', {'user_id': user_id, 'amount': '1'}).json()['reference'])
        for amount in ('0.1', '0', '-1'):
            self.assertEqual(self.admin_post('/api/admin/redemption-codes',
                {'amount': amount, 'count': 1}).status_code, 422)
        batch = self.admin_post('/api/admin/redemption-codes', {'amount': '0.1001', 'count': 2})
        self.assertEqual(batch.status_code, 200, batch.text)
        codes = batch.json()['codes']
        self.assertEqual(len(set(codes)), 2)
        listed = self.client.get('/api/admin/redemption-codes',
            headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).json()
        self.assertEqual(len(listed), 2)
        self.assertNotIn(codes[0], str(listed))
        secret = self.client.get(f"/api/admin/redemption-codes/{listed[1]['id']}/secret",
            headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']})
        self.assertEqual(secret.json()['code'], codes[0])
        exported = self.client.get('/api/admin/redemption-codes/export',
            headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']})
        self.assertEqual(exported.status_code, 200, exported.text)
        self.assertEqual(exported.encoding, 'utf-8')
        self.assertEqual(len(list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))))), 3)
        self.assertIn(codes[0], exported.text)
        selected_export = self.client.get(f"/api/admin/redemption-codes/export?ids={listed[1]['id']}",
            headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']})
        self.assertIn(codes[0], selected_export.text)
        self.assertNotIn(codes[1], selected_export.text)
        with db.SessionLocal() as session:
            legacy = session.get(RedemptionCode, listed[1]['id'])
            legacy.encrypted_code = None
            session.commit()
        legacy_secret = self.client.get(f"/api/admin/redemption-codes/{listed[1]['id']}/secret",
            headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']})
        self.assertEqual(legacy_secret.status_code, 404)
        self.assertFalse(self.client.get('/api/admin/redemption-codes',
            headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).json()[1]['can_copy'])
        self.assertEqual(self.client.delete(f"/api/admin/redemption-codes/{listed[0]['id']}",
            headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).status_code, 200)
        self.login('redeemer@example.com', 'user-password-123')
        self.assertEqual(self.admin_post('/api/admin/redemption-codes',
            {'amount': '1', 'count': 1}).status_code, 403)
        self.assertEqual(self.client.get('/api/admin/redemption-codes/export').status_code, 403)
        used = self.admin_post('/api/redemption-codes/redeem', {'code': codes[0]})
        self.assertEqual(used.status_code, 200, used.text)
        self.assertEqual(used.json()['balance'], '3.1001')
        self.assertEqual(self.admin_post('/api/redemption-codes/redeem',
            {'code': codes[0]}).status_code, 409)
        self.assertEqual(self.admin_post('/api/redemption-codes/redeem',
            {'code': codes[1]}).status_code, 409)
        self.assertEqual(self.client.get('/api/auth/me').json()['balance'], '3.1001')
        self.assertEqual(self.client.get('/api/billing?kind=redemption').json()['ledger_total'], 1)

    def test_profile_and_password_reset(self):
        registered = self.register('First Name', 'profile@example.com', 'initial-password-123')
        self.assertEqual(registered.status_code, 200, registered.text)
        user_id = registered.json()['id']
        old_session = self.client.cookies['nvp_session']
        self.assertEqual(self.client.patch('/api/auth/me', json={'name': 'Second Name'}).status_code, 403)
        self.assertEqual(self.admin_patch('/api/auth/me', {'name': 'Second Name'}).json()['name'], 'Second Name')
        self.assertEqual(self.admin_patch('/api/auth/me', {
            'current_password': 'wrong-password', 'new_password': 'new-password-12345',
        }).status_code, 403)
        changed = self.admin_patch('/api/auth/me', {
            'current_password': 'initial-password-123', 'new_password': 'new-password-12345',
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        self.client.cookies.set('nvp_session', old_session)
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)
        self.client.cookies.clear()
        self.assertEqual(self.client.post('/api/auth/login', json={
            'email': 'profile@example.com', 'password': 'initial-password-123',
        }).status_code, 401)
        self.login('profile@example.com', 'new-password-12345')
        self.assertEqual(self.client.get('/api/auth/me').json()['name'], 'Second Name')
        self.client.cookies.clear()
        self.login('admin@example.com', 'long-test-password')
        updated_admin = self.admin_patch('/api/auth/me', {
            'name': 'Updated Administrator', 'current_password': 'long-test-password',
            'new_password': 'updated-admin-password-123',
        })
        self.assertEqual(updated_admin.status_code, 200, updated_admin.text)
        bootstrap_admin()
        self.assertEqual(self.client.get('/api/auth/me').json()['name'], 'Updated Administrator')
        self.client.cookies.clear()
        self.login('admin@example.com', 'updated-admin-password-123')
        reset = self.admin_post(f'/api/admin/users/{user_id}/reset-password', {'password': 'admin-reset-12345'})
        self.assertEqual(reset.status_code, 200, reset.text)
        self.client.cookies.clear()
        self.assertEqual(self.client.post('/api/auth/login', json={
            'email': 'profile@example.com', 'password': 'new-password-12345',
        }).status_code, 401)
        self.login('profile@example.com', 'admin-reset-12345')

    def test_public_model_catalog_respects_private_groups(self):
        with db.SessionLocal.begin() as session:
            account = UpstreamAccount(name='catalog-account', base_url='https://example.com', encrypted_key='test')
            disabled = UpstreamAccount(name='disabled-account', base_url='https://example.com',
                                       encrypted_key='test', enabled=False)
            public = UpstreamGroup(name='Public Group')
            private = UpstreamGroup(name='Private Group', is_private=True)
            session.add_all([account, disabled, public, private])
            session.flush()
            for group, name in ((public, 'public-model'), (private, 'private-model')):
                mapping = ModelMapping(group_id=group.id, public_name=name, upstream_model=name,
                                       upstream_account_id=disabled.id)
                session.add(mapping)
                session.flush()
                session.add(ModelRoute(model_mapping_id=mapping.id, account_id=account.id,
                                       upstream_model=name))
                session.add(PriceVersion(model_mapping_id=mapping.id, amount=Decimal('0.2500')))
            private_id = private.id
        anonymous = self.client.get('/api/public/models')
        self.assertEqual(anonymous.status_code, 200, anonymous.text)
        self.assertEqual([row['name'] for row in anonymous.json()], ['public-model'])
        self.login('admin@example.com', 'long-test-password')
        self.assertEqual({row['name'] for row in self.client.get('/api/public/models').json()},
                         {'public-model', 'private-model'})
        self.assertEqual({row['name'] for row in self.client.get('/api/models').json()},
                         {'public-model', 'private-model'})
        self.client.cookies.clear()
        plaza = self.client.get('/models')
        self.assertEqual(plaza.status_code, 200, plaza.text)
        self.assertIn('<div id="root"></div>', plaza.text)
        registered = self.register('Catalog User', 'catalog@example.com', 'catalog-password-123')
        self.assertEqual(registered.status_code, 200, registered.text)
        self.assertEqual(len(self.client.get('/api/public/models').json()), 1)
        with db.SessionLocal.begin() as session:
            session.add(GroupMember(group_id=private_id, user_id=registered.json()['id']))
        rows = self.client.get('/api/public/models').json()
        self.assertEqual({row['name'] for row in rows}, {'public-model', 'private-model'})
        self.assertEqual(next(row for row in rows if row['is_private'])['group_name'], 'Private Group')
        self.client.cookies.clear()
        self.assertEqual([row['name'] for row in self.client.get('/api/public/models').json()],
                         ['public-model'])
        self.register('Unassigned User', 'unassigned@example.com', 'unassigned-password-123')
        self.assertEqual([row['name'] for row in self.client.get('/api/public/models').json()],
                         ['public-model'])

    def test_announcement_audience_and_beijing_schedule(self):
        self.login('admin@example.com', 'long-test-password')
        now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
        def create(title, private=False, start=None, end=None):
            result = self.admin_post('/api/admin/announcements', {
                'title': title, 'body': f'{title} body', 'is_private': private,
                'starts_at': start.isoformat() if start else None,
                'ends_at': end.isoformat() if end else None,
            })
            self.assertEqual(result.status_code, 200, result.text)
            return result.json()
        public = create('Public', end=now + timedelta(hours=1))
        create('Private', private=True)
        create('Future', start=now + timedelta(hours=1))
        create('Expired', start=now - timedelta(hours=2), end=now - timedelta(hours=1))
        temporary = create('Temporary')
        self.assertEqual(self.client.delete(f'/api/admin/announcements/{temporary["id"]}', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).status_code, 200)
        revised = self.admin_patch(f'/api/admin/announcements/{public["id"]}', {
            'title': 'Revised', 'body': 'New text', 'is_private': False,
            'ends_at': (now + timedelta(hours=1)).isoformat(),
        })
        self.assertEqual(revised.status_code, 200, revised.text)
        self.assertEqual(len(self.client.get('/api/admin/announcements', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).json()), 4)
        self.assertEqual(self.admin_post('/api/admin/announcements', {
            'title': 'Naive', 'body': 'Invalid', 'starts_at': '2026-10-06T12:00:00',
        }).status_code, 422)
        self.client.cookies.clear()
        self.assertEqual([row['title'] for row in self.client.get('/api/public/announcements').json()], ['Revised'])
        self.register('Notice User', 'notices@example.com', 'notice-password-123')
        self.assertEqual({row['title'] for row in self.client.get('/api/public/announcements').json()},
                         {'Revised', 'Private'})
        self.assertEqual(self.admin_patch(f'/api/admin/announcements/{public["id"]}', {
            'title': 'Wrong Role', 'body': 'Not allowed',
        }).status_code, 403)

    def test_admin_configuration_updates_single_administrator(self):
        changed = get_business_config().model_copy(update={
            'admin': AdminConfig(email='root@example.com', name='New Administrator',
                                 password='replacement-password-123', max_concurrency=7),
        })
        with patch('app.bootstrap.get_business_config', return_value=changed):
            bootstrap_admin()
        with db.SessionLocal() as session:
            administrators = session.scalars(select(User).where(User.is_admin.is_(True))).all()
            self.assertEqual(len(administrators), 1)
            self.assertEqual(administrators[0].email, 'root@example.com')
            self.assertEqual(administrators[0].display_name, 'Test Administrator')
            self.assertEqual(administrators[0].max_concurrency, 7)
            self.assertTrue(verify_password('long-test-password', administrators[0].password_hash))

    def test_registration_user_management_and_key_distribution(self):
        self.assertTrue(self.client.get('/api/auth/options').json()['registration_enabled'])
        self.login('admin@example.com', 'long-test-password')
        settings = self.client.get('/api/admin/registration-settings', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).json()
        disabled = self.client.put('/api/admin/registration-settings', json={**settings, 'enabled': False},
                                   headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']})
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertFalse(self.client.get('/api/auth/options').json()['registration_enabled'])
        self.assertEqual(self.client.post('/api/auth/registration-code', json={
            'email': 'blocked@example.com',
        }).status_code, 403)
        self.client.put('/api/admin/registration-settings', json={**settings, 'enabled': True},
                        headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']})
        self.client.cookies.clear()
        registered = self.register('Registered User', 'registered@example.com', 'strong-user-password')
        self.assertEqual(registered.status_code, 200, registered.text)
        user_id = registered.json()['id']
        self.assertEqual(registered.json()['role'], 'user')
        self.assertEqual(registered.json()['max_concurrency'], 2)
        self.assertEqual(self.client.get('/api/admin/users',
                                         headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).status_code, 403)
        self.assertEqual(self.client.post('/api/admin/credit', json={
            'user_id': user_id, 'amount': '10', 'reference': 'forbidden',
        }, headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).status_code, 403)

        self.client.cookies.clear()
        admin = self.login('admin@example.com', 'long-test-password')
        self.assertEqual(admin['name'], 'Test Administrator')
        self.assertEqual(admin['max_concurrency'], 5)
        self.assertEqual(self.admin_post('/api/admin/credit', {
            'user_id': admin['id'], 'amount': '8.0000', 'reference': 'admin-own',
        }).status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me').json()['balance'], '8.0000')

        first_key = self.admin_post(f'/api/admin/users/{user_id}/keys', {'name': 'service-a'})
        second_key = self.admin_post(f'/api/admin/users/{user_id}/keys', {'name': 'service-b'})
        self.assertEqual(first_key.status_code, 200, first_key.text)
        self.assertNotEqual(first_key.json()['key'], second_key.json()['key'])
        self.assertEqual(len(self.client.get(f'/api/admin/users/{user_id}/keys',
                                             headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).json()), 2)
        self.assertEqual(self.admin_patch(f'/api/admin/users/{user_id}', {
            'name': 'Renamed User', 'max_concurrency': 1,
        }).status_code, 200)
        self.assertEqual(self.admin_patch(f'/api/admin/users/{admin["id"]}', {'is_active': False}).status_code, 403)
        self.assertEqual(self.admin_patch(f'/api/admin/users/{user_id}', {'is_active': False}).status_code, 200)

        self.client.cookies.clear()
        self.assertEqual(self.client.post('/api/auth/login', json={
            'email': 'registered@example.com', 'password': 'strong-user-password',
        }).status_code, 401)
        self.assertEqual(self.client.get('/v1/jobs/unknown', headers={
            'Authorization': 'Bearer ' + first_key.json()['key'],
        }).status_code, 401)

        self.login('admin@example.com', 'long-test-password')
        self.assertEqual(self.admin_patch(f'/api/admin/users/{user_id}', {'is_active': True}).status_code, 200)
        self.client.cookies.clear()
        self.assertEqual(self.login('registered@example.com', 'strong-user-password')['name'], 'Renamed User')
        self.client.cookies.clear()
        self.login('admin@example.com', 'long-test-password')
        deleted = self.client.delete(f'/api/admin/users/{user_id}',
                                     headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']})
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(self.client.delete(f'/api/admin/users/{admin["id"]}',
                                            headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).status_code, 403)
        self.assertFalse(any(row['id'] == user_id for row in self.client.get('/api/admin/users',
                          headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).json()))
        self.client.cookies.clear()
        self.assertEqual(self.client.post('/api/auth/login', json={
            'email': 'registered@example.com', 'password': 'strong-user-password',
        }).status_code, 401)
        self.login('admin@example.com', 'long-test-password')
        archived = self.client.get('/api/admin/users?include_deleted=true',
                                   headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).json()
        self.assertTrue(next(row for row in archived if row['id'] == user_id)['deleted_at'])
        self.assertEqual(self.admin_patch(f'/api/admin/users/{user_id}', {'is_active': True}).status_code, 200)
        self.client.cookies.clear()
        self.assertEqual(self.login('registered@example.com', 'strong-user-password')['name'], 'Renamed User')
        self.assertEqual(self.client.get('/v1/jobs/unknown', headers={
            'Authorization': 'Bearer ' + first_key.json()['key'],
        }).status_code, 401)

    def test_user_has_no_concurrency_limit(self):
        self.login('admin@example.com', 'long-test-password')
        upstream = self.admin_post('/api/admin/upstreams', {
            'name': 'test', 'base_url': 'http://127.0.0.1:9999/v1', 'api_key': 'upstream-secret',
        }).json()
        self.assertEqual(self.admin_post('/api/admin/mappings', {
            'public_name': 'model', 'upstream_account_id': upstream['id'],
            'upstream_model': 'image', 'price': '1.0000', 'max_concurrency': 5,
        }).status_code, 200)
        created = self.admin_post('/api/admin/users', {
            'name': 'Limited User', 'email': 'limited@example.com',
            'password': 'limited-password-123', 'max_concurrency': 1,
        }).json()
        self.assertEqual(self.admin_post('/api/admin/credit', {
            'user_id': created['id'], 'amount': '10.0000', 'reference': 'funded',
        }).status_code, 200)
        key = self.admin_post(f'/api/admin/users/{created["id"]}/keys', {'name': 'worker'}).json()['key']
        headers = {'Authorization': 'Bearer ' + key, 'Idempotency-Key': 'first'}
        payload = {'model': 'model', 'prompt': 'Sunrise'}
        first = self.client.post('/v1/images/generations', json=payload, headers=headers)
        self.assertEqual(first.status_code, 202, first.text)
        second = self.client.post('/v1/images/generations', json=payload,
                                  headers={**headers, 'Idempotency-Key': 'second'})
        self.assertEqual(second.status_code, 202, second.text)
        self.assertEqual(self.client.delete(f'/api/admin/users/{created["id"]}',
                                            headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).status_code, 409)
        self.assertEqual(self.admin_patch(f'/api/admin/users/{created["id"]}', {'is_active': False}).status_code, 200)
        with patch('app.worker.OpenAIImageAdapter.generate', return_value={'data': [{'url': 'https://example.com/image.png'}]}):
            self.assertTrue(run_once())
            self.assertTrue(run_once())
        with db.SessionLocal() as session:
            settled = session.get(User, created['id'])
            self.assertEqual(settled.balance, 8)
            self.assertEqual(settled.reserved, 0)
        self.assertEqual(self.client.delete(f'/api/admin/users/{created["id"]}',
                                            headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).status_code, 200)

    def test_private_group_membership_controls_keys_models_and_existing_keys(self):
        admin = self.login('admin@example.com', 'long-test-password')
        first = self.admin_post('/api/admin/users', {
            'name': 'Allowed', 'email': 'allowed@example.com', 'password': 'allowed-password-123',
        }).json()
        other = self.admin_post('/api/admin/users', {
            'name': 'Other', 'email': 'other@example.com', 'password': 'other-password-123',
        }).json()
        recipients = self.client.get('/api/admin/group-recipients', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).json()
        self.assertEqual({row['id'] for row in recipients}, {admin['id'], first['id'], other['id']})
        account = self.admin_post('/api/admin/upstreams', {
            'name': 'private-upstream', 'base_url': 'http://127.0.0.1:9999/v1',
            'api_key': 'secret',
        }).json()
        self.assertEqual(self.admin_post('/api/admin/groups', {
            'name': 'invalid', 'is_private': True, 'member_ids': [999999],
        }).status_code, 422)
        group = self.admin_post('/api/admin/groups', {
            'name': 'private', 'is_private': True, 'member_ids': [first['id'], admin['id']],
            'account_ids': [],
        }).json()
        saved_group = next(row for row in self.client.get('/api/admin/groups', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).json() if row['id'] == group['id'])
        self.assertTrue(saved_group['is_private'])
        self.assertEqual(set(saved_group['member_ids']), {first['id'], admin['id']})
        self.assertEqual(saved_group['account_ids'], [])
        self.assertEqual(self.admin_post('/api/admin/mappings', {
            'group_id': group['id'], 'public_name': 'private-art', 'price': '1.0000',
            'routes': [{'account_id': account['id'], 'upstream_model': 'image'}],
        }).status_code, 422)
        self.assertEqual(self.admin_post('/api/admin/groups', {
            'id': group['id'], 'name': 'private', 'is_private': True,
            'member_ids': [first['id'], admin['id']], 'account_ids': [account['id']],
        }).status_code, 200)
        self.assertEqual(self.admin_post('/api/admin/mappings', {
            'group_id': group['id'], 'public_name': 'private-art', 'price': '1.0000',
            'routes': [{'account_id': account['id'], 'upstream_model': 'image'}],
        }).status_code, 200)
        self.assertEqual(self.admin_post(f'/api/admin/users/{other["id"]}/keys', {
            'name': 'forbidden', 'group_id': group['id'],
        }).status_code, 404)
        self.client.cookies.clear()
        self.login('other@example.com', 'other-password-123')
        self.assertNotIn(group['id'], [item['id'] for item in self.client.get('/api/groups').json()])
        self.assertNotIn('private-art', [item['name'] for item in self.client.get('/api/models').json()])
        self.assertEqual(self.client.post('/api/keys', json={
            'name': 'forbidden', 'group_id': group['id'],
        }, headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).status_code, 404)
        self.client.cookies.clear()
        self.login('allowed@example.com', 'allowed-password-123')
        self.assertIn(group['id'], [item['id'] for item in self.client.get('/api/groups').json()])
        self.assertIn('private-art', [item['name'] for item in self.client.get('/api/models').json()])
        key_response = self.client.post('/api/keys', json={
            'name': 'allowed', 'group_id': group['id'],
        }, headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']})
        self.assertEqual(key_response.status_code, 200, key_response.text)
        key = key_response.json()['key']
        self.assertEqual(self.client.get('/v1/models', headers={
            'Authorization': 'Bearer ' + key,
        }).status_code, 200)
        self.client.cookies.clear()
        self.login('admin@example.com', 'long-test-password')
        self.assertEqual(self.admin_post('/api/admin/groups', {
            'id': group['id'], 'name': 'private', 'is_private': True,
            'member_ids': [admin['id']], 'account_ids': [account['id']],
        }).status_code, 200)
        self.assertEqual(self.client.get('/v1/models', headers={
            'Authorization': 'Bearer ' + key,
        }).status_code, 401)
        self.assertEqual(self.client.post('/v1/images/generations', json={
            'model': 'private-art', 'prompt': 'Denied',
        }, headers={'Authorization': 'Bearer ' + key, 'Idempotency-Key': 'revoked-access'}).status_code, 401)

    def test_admin_configuration_edit_archive_and_restore(self):
        admin = self.login('admin@example.com', 'long-test-password')
        account = self.admin_post('/api/admin/upstreams', {
            'name': 'editable-account', 'base_url': 'http://127.0.0.1:9999/v1',
            'api_key': 'initial-key',
        }).json()
        changed = self.admin_patch(f'/api/admin/upstreams/{account["id"]}', {
            'name': 'renamed-account', 'base_url': 'https://example.com/v1',
            'api_key': 'replacement-key', 'max_concurrency': 3, 'enabled': True,
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        accounts = self.client.get('/api/admin/upstreams', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).json()
        self.assertEqual(next(row for row in accounts if row['id'] == account['id'])['name'], 'renamed-account')
        group = self.admin_post('/api/admin/groups', {
            'name': 'editable-group', 'account_ids': [account['id']],
        }).json()
        self.assertEqual(self.admin_post('/api/admin/groups', {
            'id': group['id'], 'name': 'renamed-group', 'account_ids': [account['id']],
        }).status_code, 200)
        self.assertEqual(next(row for row in self.client.get('/api/admin/groups', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).json() if row['id'] == group['id'])['name'], 'renamed-group')
        key = self.admin_post(f'/api/admin/users/{admin["id"]}/keys', {
            'name': 'group-key', 'group_id': group['id'],
        }).json()['key']
        mapping = self.admin_post('/api/admin/mappings', {
            'group_id': group['id'], 'public_name': 'editable-model', 'price': '1',
            'routes': [{'account_id': account['id'], 'upstream_model': 'image'}],
        }).json()
        self.assertEqual(self.admin_post('/api/admin/mappings', {
            'id': mapping['id'], 'group_id': group['id'], 'public_name': 'renamed-model',
            'price': '2', 'routes': [{'account_id': account['id'], 'upstream_model': 'image-v2'}],
        }).status_code, 200)
        self.assertEqual(len(self.client.get('/api/admin/mappings', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).json()), 1)
        delete = lambda path: self.client.delete(path, headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        })
        self.assertEqual(delete(f'/api/admin/upstreams/{account["id"]}').status_code, 409)
        self.assertEqual(delete(f'/api/admin/mappings/{mapping["id"]}').status_code, 200)
        self.assertEqual(self.client.get('/api/admin/mappings', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).json(), [])
        archived = self.client.get('/api/admin/mappings?include_deleted=true', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).json()[0]
        self.assertIsNotNone(archived['deleted_at'])
        self.assertEqual(self.admin_post(f'/api/admin/mappings/{mapping["id"]}/restore', {}).status_code, 200)
        self.assertFalse(self.client.get('/api/admin/mappings', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).json()[0]['enabled'])
        self.assertEqual(delete(f'/api/admin/mappings/{mapping["id"]}').status_code, 200)
        self.assertEqual(delete(f'/api/admin/groups/{group["id"]}').status_code, 200)
        self.assertEqual(self.client.get('/v1/models', headers={
            'Authorization': 'Bearer ' + key,
        }).status_code, 401)
        self.assertEqual(self.admin_post(f'/api/admin/groups/{group["id"]}/restore', {}).status_code, 200)
        self.assertEqual(self.client.get('/v1/models', headers={
            'Authorization': 'Bearer ' + key,
        }).status_code, 401)
        self.assertEqual(delete(f'/api/admin/upstreams/{account["id"]}').status_code, 200)
        self.assertEqual(self.admin_post(f'/api/admin/mappings/{mapping["id"]}/restore', {}).status_code, 409)
        self.assertEqual(self.admin_post(f'/api/admin/upstreams/{account["id"]}/restore', {}).status_code, 200)

    def test_admin_can_edit_user_and_delete_uncertain_job(self):
        self.login('admin@example.com', 'long-test-password')
        account = self.admin_post('/api/admin/upstreams', {
            'name': 'uncertain-account', 'base_url': 'http://127.0.0.1:9999/v1',
            'api_key': 'secret',
        }).json()
        self.assertEqual(self.admin_post('/api/admin/mappings', {
            'public_name': 'uncertain-model', 'upstream_account_id': account['id'],
            'upstream_model': 'image', 'price': '1',
        }).status_code, 200)
        user = self.admin_post('/api/admin/users', {
            'name': 'Before', 'email': 'before@example.com', 'password': 'password-123456',
        }).json()
        self.assertEqual(self.admin_patch(f'/api/admin/users/{user["id"]}', {
            'name': 'After', 'email': 'after@example.com', 'max_concurrency': 4,
        }).status_code, 200)
        searched = self.client.get('/api/admin/users?search=after@example.com&limit=1', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).json()
        self.assertEqual([row['id'] for row in searched], [user['id']])
        self.assertEqual(self.client.get('/api/admin/users?search=after@example.com&limit=1&offset=1', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        }).json(), [])
        self.assertEqual(self.admin_post('/api/admin/credit', {
            'user_id': user['id'], 'amount': '10', 'reference': 'uncertain-credit',
        }).status_code, 200)
        key = self.admin_post(f'/api/admin/users/{user["id"]}/keys', {
            'name': 'key',
        }).json()['key']
        response = self.client.post('/v1/images/generations', json={
            'model': 'uncertain-model', 'prompt': 'Test',
        }, headers={'Authorization': 'Bearer ' + key, 'Idempotency-Key': 'uncertain-delete'})
        self.assertEqual(response.status_code, 202, response.text)
        job_id = response.json()['id']
        with db.SessionLocal.begin() as session:
            session.get(GenerationJob, job_id).status = JobStatus.UNCERTAIN
        deleted = self.client.delete(f'/api/admin/uncertain/{job_id}', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf'],
        })
        self.assertEqual(deleted.status_code, 200, deleted.text)
        with db.SessionLocal() as session:
            job = session.get(GenerationJob, job_id)
            owner = session.get(User, user['id'])
            self.assertEqual(job.status, JobStatus.FAILED)
            self.assertIsNotNone(job.hidden_at)
            self.assertEqual(owner.reserved, 0)
            self.assertEqual(owner.balance, 10)

    def test_group_scoping_failover_and_billing_filters(self):
        self.login('admin@example.com', 'long-test-password')
        first = self.admin_post('/api/admin/upstreams', {
            'name': 'primary', 'base_url': 'http://127.0.0.1:9999/v1',
            'api_key': 'one', 'max_concurrency': 1,
        }).json()
        second = self.admin_post('/api/admin/upstreams', {
            'name': 'backup', 'base_url': 'http://127.0.0.1:9999/v1',
            'api_key': 'two', 'max_concurrency': 1,
        }).json()
        group = self.admin_post('/api/admin/groups', {
            'name': 'team', 'account_ids': [first['id'], second['id']],
            'max_concurrency': 2,
        }).json()
        mapped = self.admin_post('/api/admin/mappings', {
            'group_id': group['id'], 'public_name': 'art', 'price': '1.0000',
            'routes': [{'account_id': first['id'], 'upstream_model': 'image-a'},
                       {'account_id': second['id'], 'upstream_model': 'image-b'}],
        })
        self.assertEqual(mapped.status_code, 200, mapped.text)
        self.assertEqual(self.admin_post('/api/admin/mappings', {
            'public_name': 'art', 'upstream_account_id': first['id'],
            'upstream_model': 'other', 'price': '2.0000',
        }).status_code, 200)
        self.assertEqual(len(self.client.get('/api/admin/mappings', headers={
            'X-CSRF-Token': self.client.cookies['nvp_csrf']}).json()), 2)
        admin_id = self.client.get('/api/auth/me').json()['id']
        self.assertEqual(self.admin_post('/api/admin/credit', {
            'user_id': admin_id, 'amount': '10', 'reference': 'group-test',
        }).status_code, 200)
        group_key = self.admin_post(f'/api/admin/users/{admin_id}/keys', {
            'name': 'team-key', 'group_id': group['id'],
        }).json()['key']
        default_key = self.admin_post(f'/api/admin/users/{admin_id}/keys', {
            'name': 'default-key', 'group_id': 1,
        }).json()['key']
        self.assertEqual(self.client.get('/v1/models', headers={
            'Authorization': 'Bearer ' + default_key}).json()['data'][0]['id'], 'art')
        self.assertEqual(self.client.get('/v1/models', headers={
            'Authorization': 'Bearer ' + group_key}).json()['data'][0]['id'], 'art')
        first_job = self.client.post('/v1/images/generations', json={
            'model': 'art', 'prompt': 'First'}, headers={
            'Authorization': 'Bearer ' + group_key, 'Idempotency-Key': 'group-first'})
        self.assertEqual(first_job.status_code, 202, first_job.text)
        self.assertEqual(self.client.get('/v1/jobs/' + first_job.json()['id'], headers={
            'Authorization': 'Bearer ' + default_key}).status_code, 404)
        self.assertEqual(self.client.post('/v1/images/generations', json={
            'model': 'art', 'prompt': 'First'}, headers={
            'Authorization': 'Bearer ' + default_key, 'Idempotency-Key': 'group-first'}).status_code, 409)
        second_job = self.client.post('/v1/images/generations', json={
            'model': 'art', 'prompt': 'Second'}, headers={
            'Authorization': 'Bearer ' + group_key, 'Idempotency-Key': 'group-second'})
        self.assertEqual(second_job.status_code, 202, second_job.text)
        third_job = self.client.post('/v1/images/generations', json={
            'model': 'art', 'prompt': 'Third'}, headers={
            'Authorization': 'Bearer ' + group_key, 'Idempotency-Key': 'group-third'})
        self.assertEqual(third_job.status_code, 202, third_job.text)
        with db.SessionLocal() as session:
            claimed = claim_job(session, 180)
            self.assertEqual(claimed.upstream_account_id, first['id'])
            alternate = claim_job(session, 180)
            self.assertEqual(alternate.upstream_account_id, second['id'])
            self.assertIsNone(claim_job(session, 180))
        with db.SessionLocal() as session:
            with session.begin():
                for job in session.scalars(select(GenerationJob)):
                    job.status = JobStatus.QUEUED
        response = httpx.Response(429, request=httpx.Request('POST', 'http://127.0.0.1:9999/v1/images/generations'))
        failure = httpx.HTTPStatusError('busy', request=response.request, response=response)
        calls = []
        def generate(adapter, job):
            calls.append((adapter.account.id, job.upstream_model))
            if adapter.account.id == first['id']:
                raise failure
            return {'data': [{'url': 'https://example.com/image.png'}]}
        with patch('app.worker.OpenAIImageAdapter.generate', generate):
            self.assertTrue(run_once(first_job.json()['id']))
        self.assertEqual(calls, [(first['id'], 'image-a'), (second['id'], 'image-b')])
        today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        billing = self.client.get(f'/api/billing?model=art&date_from={today}').json()
        self.assertEqual(billing['usage_total'], 1)
        self.assertEqual(billing['usage'][0]['amount'], '1.0000')
        usage_id = billing['usage'][0]['id']
        self.assertEqual(self.admin_post('/api/billing/delete', {'usage_ids': [usage_id]}).status_code, 200)
        self.assertEqual(self.client.get('/api/billing').json()['usage_total'], 0)
        self.assertEqual(self.client.get('/api/billing').json()['balance'], '9.0000')
        self.assertEqual(self.admin_patch(f'/api/admin/upstreams/{first["id"]}', {
            'max_concurrency': 1, 'enabled': False,
        }).status_code, 200)
        fallback = self.client.post('/v1/images/generations', json={
            'model': 'art', 'prompt': 'Backup only'}, headers={
            'Authorization': 'Bearer ' + group_key, 'Idempotency-Key': 'backup-only'})
        self.assertEqual(fallback.status_code, 202, fallback.text)
        with db.SessionLocal() as session:
            self.assertEqual(session.get(GenerationJob, fallback.json()['id']).upstream_account_id,
                             second['id'])

    def test_novelai_overlap_requires_reconciliation(self):
        self.login('admin@example.com', 'long-test-password')
        account = self.admin_post('/api/admin/upstreams', {
            'name': 'novelai-overlap', 'provider': 'novelai',
            'base_url': 'http://127.0.0.1:9999', 'api_key': 'secret',
            'max_concurrency': 2,
        }).json()
        self.assertEqual(self.admin_post('/api/admin/mappings', {
            'public_name': 'anime', 'upstream_account_id': account['id'],
            'upstream_model': 'nai-diffusion-4-5-full', 'price': '0.1000',
        }).status_code, 200)
        user_id = self.client.get('/api/auth/me').json()['id']
        self.assertEqual(self.admin_post('/api/admin/credit', {
            'user_id': user_id, 'amount': '100', 'reference': 'overlap',
        }).status_code, 200)
        key = self.admin_post(f'/api/admin/users/{user_id}/keys', {'name': 'overlap'}).json()['key']
        ids = []
        for index in range(2):
            response = self.client.post('/v1/images/generations', json={
                'model': 'anime', 'prompt': f'Image {index}',
            }, headers={'Authorization': 'Bearer ' + key,
                        'Idempotency-Key': f'overlap-{index}'})
            self.assertEqual(response.status_code, 202, response.text)
            ids.append(response.json()['id'])
        with db.SessionLocal() as session:
            self.assertEqual(claim_job(session, 180).id, ids[0])
            self.assertEqual(claim_job(session, 180).id, ids[1])
            session.expire_all()
            self.assertTrue(all(session.get(GenerationJob, job_id).billing_overlap for job_id in ids))

    def test_novelai_generation_uses_actual_anlas_and_serves_image(self):
        self.login('admin@example.com', 'long-test-password')
        account = self.admin_post('/api/admin/upstreams', {
            'name': 'novelai', 'provider': 'novelai', 'opus_free': False,
            'base_url': 'http://127.0.0.1:9999', 'api_key': 'upstream-secret',
        }).json()
        self.assertEqual(self.admin_post('/api/admin/mappings', {
            'public_name': 'anime', 'upstream_account_id': account['id'],
            'upstream_model': 'nai-diffusion-4-5-full', 'price': '0.1000',
        }).status_code, 200)
        self.assertEqual(self.client.get('/api/admin/mappings',
                                         headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).json()[0]['extra_amount'], '0.1000')
        admin_id = self.client.get('/api/auth/me').json()['id']
        self.assertEqual(self.admin_post('/api/admin/credit', {
            'user_id': admin_id, 'amount': '10', 'reference': 'novelai-test',
        }).status_code, 200)
        key = self.admin_post(f'/api/admin/users/{admin_id}/keys', {'name': 'generate'}).json()['key']
        headers = {'Authorization': 'Bearer ' + key, 'Idempotency-Key': 'novelai-1'}
        payload = {'model': 'anime', 'prompt': 'a red kite in a clear sky',
                   'parameters': {'steps': 23, 'scale': 4, 'seed': 42}}
        submitted = self.client.post('/v1/images/generations', json=payload, headers=headers)
        self.assertEqual(submitted.status_code, 202, submitted.text)
        self.assertEqual(submitted.json()['anlas_cost'], 17)
        self.assertEqual(self.client.post('/v1/images/generations', json={
            **payload, 'parameters': {'steps': 24}}, headers=headers).status_code, 409)
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, 'w') as archive:
            archive.writestr('image_0.png', b'\x89PNG\r\n\x1a\nimage')
        request = httpx.Request('POST', 'http://127.0.0.1:9999/ai/generate-image')
        response = httpx.Response(200, content=archive_bytes.getvalue(), request=request)
        balance_request = httpx.Request('GET', 'http://127.0.0.1:9999/user/subscription')
        balances = [httpx.Response(200, json={'trainingStepsLeft': {
            'fixedTrainingStepsLeft': value, 'purchasedTrainingSteps': 0}}, request=balance_request)
                    for value in (100, 85)]
        with tempfile.TemporaryDirectory() as directory:
            with patch('app.upstream.IMAGE_DIR', Path(directory)), patch('app.api.user.IMAGE_DIR', Path(directory)), \
                 patch('app.upstream.httpx.get', side_effect=balances), \
                 patch('app.upstream.httpx.post', return_value=response) as send:
                self.assertTrue(run_once())
                sent = send.call_args.kwargs['json']
                self.assertEqual(sent['model'], 'nai-diffusion-4-5-full')
                self.assertEqual(sent['parameters']['v4_prompt']['caption']['base_caption'], payload['prompt'])
                job = self.client.get('/v1/jobs/' + submitted.json()['id'], headers=headers).json()
                self.assertEqual(job['status'], 'succeeded')
                self.assertEqual(job['anlas_cost'], 15)
                self.assertEqual(job['amount'], '1.6000')
                with db.SessionLocal() as session:
                    self.assertIsNone(session.get(GenerationJob, job['id']).result)
                self.assertEqual(self.client.get(job['result']['data'][0]['url']).status_code, 200)
                self.assertEqual(self.client.get(f'/v1/jobs/{job["id"]}/image',
                                                 headers={'Authorization': 'Bearer ' + key}).status_code, 200)
                self.assertEqual(self.client.get('/api/billing').json()['balance'], '8.4000')

    def test_usage_visibility_filters_and_admin_deletion(self):
        self.login('admin@example.com', 'long-test-password')
        admin_id = self.client.get('/api/auth/me').json()['id']
        account = self.admin_post('/api/admin/upstreams', {
            'name': 'usage-upstream', 'base_url': 'http://127.0.0.1:9999/v1',
            'api_key': 'upstream-secret',
        }).json()
        self.admin_post('/api/admin/mappings', {
            'public_name': 'usage-model', 'upstream_account_id': account['id'],
            'upstream_model': 'image', 'price': '1.0000',
        })
        user = self.admin_post('/api/admin/users', {
            'name': 'Usage User', 'email': 'usage@example.com',
            'password': 'usage-password-123',
        }).json()
        for user_id in (admin_id, user['id']):
            self.admin_post('/api/admin/credit', {
                'user_id': user_id, 'amount': '10', 'reference': f'usage-{user_id}',
            })
        admin_key = self.admin_post(f'/api/admin/users/{admin_id}/keys', {'name': 'usage'}).json()['key']
        user_key = self.admin_post(f'/api/admin/users/{user["id"]}/keys', {'name': 'usage'}).json()['key']
        jobs = []
        for index, key in enumerate((admin_key, user_key, user_key)):
            response = self.client.post('/v1/images/generations',
                json={'model': 'usage-model', 'prompt': f'usage {index}'},
                headers={'Authorization': 'Bearer ' + key,
                         'Idempotency-Key': f'usage-{index}'})
            self.assertEqual(response.status_code, 202, response.text)
            jobs.append(response.json()['id'])
            with patch('app.worker.OpenAIImageAdapter.generate',
                       return_value={'data': [{'url': 'https://example.com/image.png'}]}):
                self.assertTrue(run_once())
        self.assertEqual(self.client.get('/api/usage').json()['total'], 3)
        self.assertEqual(self.client.get('/api/usage/models').json(), ['usage-model'])
        filtered = self.client.get(f'/api/usage?user_id={user["id"]}&status=succeeded&model=usage-model').json()
        self.assertEqual(filtered['total'], 2)
        self.assertTrue(all(row['user_name'] == 'Usage User' for row in filtered['items']))
        self.assertEqual(self.client.get('/api/usage?limit=1&offset=1').json()['total'], 3)
        self.assertEqual(self.client.get('/api/usage?search=' + jobs[0][:8]).json()['total'], 1)
        usage_csv = self.client.get(f'/api/usage/export?user_id={user["id"]}&status=succeeded')
        self.assertEqual(usage_csv.status_code, 200, usage_csv.text)
        self.assertEqual(len(list(csv.reader(io.StringIO(usage_csv.content.decode('utf-8-sig'))))), 3)
        selected_csv = self.client.get(f'/api/usage/export?ids={jobs[0]}')
        self.assertIn(jobs[0], selected_csv.text)
        self.assertNotIn(jobs[1], selected_csv.text)
        with db.SessionLocal() as session:
            self.assertTrue(all(session.get(GenerationJob, job_id).result is None for job_id in jobs))

        self.client.cookies.clear()
        self.login('usage@example.com', 'usage-password-123')
        self.assertEqual(self.client.get('/api/usage').json()['total'], 2)
        scoped_csv = self.client.get(f'/api/usage/export?ids={jobs[0]}&ids={jobs[2]}')
        self.assertNotIn(jobs[0], scoped_csv.text)
        self.assertIn(jobs[2], scoped_csv.text)
        self.assertEqual(self.client.get('/api/usage/models').json(), ['usage-model'])
        self.assertEqual(self.client.get(f'/api/usage?user_id={admin_id}').json()['total'], 2)
        self.assertEqual(self.client.post('/api/usage/delete', json={'ids': [jobs[0]]},
                         headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']}).status_code, 403)
        self.client.cookies.clear()
        self.login('admin@example.com', 'long-test-password')
        self.assertEqual(self.admin_post('/api/usage/delete', {'ids': jobs[:2]}).json()['deleted'], 2)
        self.assertEqual(self.client.get('/api/usage').json()['total'], 1)
        with db.SessionLocal() as session:
            self.assertIsNotNone(session.get(GenerationJob, jobs[0]).hidden_at)
            self.assertIsNotNone(session.scalar(select(UsageRecord).where(UsageRecord.job_id == jobs[1])))
        self.assertEqual(self.admin_post('/api/usage/delete', {'ids': [jobs[2]]}).json()['deleted'], 1)
        self.assertEqual(self.client.get('/api/usage').json()['total'], 0)
        with db.SessionLocal() as session:
            self.assertEqual(len(session.scalars(select(UsageRecord)).all()), 3)
        pending = self.client.post('/v1/images/generations',
            json={'model': 'usage-model', 'prompt': 'Still running'},
            headers={'Authorization': 'Bearer ' + admin_key,
                     'Idempotency-Key': 'usage-pending'})
        self.assertEqual(pending.status_code, 202, pending.text)
        self.assertEqual(self.admin_post('/api/usage/delete',
                         {'ids': [pending.json()['id']]}).status_code, 409)
        self.assertEqual(self.client.get('/api/usage').json()['total'], 1)

    def test_openai_image_is_delivered_from_disk(self):
        account = UpstreamAccount(base_url='https://images.example/v1',
                                  encrypted_key=encrypt_upstream_key('secret'))
        job = GenerationJob(id='openai-image-test', upstream_model='image',
                            prompt='A mountain', size='512x512')
        request = httpx.Request('POST', 'https://images.example/v1/images/generations')
        response = httpx.Response(200, json={'data': [{'url': 'https://images.example/out.png'}]},
                                  request=request)
        image_request = httpx.Request('GET', 'https://images.example/out.png')
        image = httpx.Response(200, content=b'\x89PNG\r\n\x1a\nimage', request=image_request)
        with tempfile.TemporaryDirectory() as directory, \
             patch('app.upstream.IMAGE_DIR', Path(directory)), \
             patch('app.upstream.httpx.post', return_value=response), \
             patch('app.upstream.httpx.get', return_value=image):
            result = OpenAIImageAdapter(account, 5).generate(job)
            self.assertEqual(result['data'][0]['url'], '/api/jobs/openai-image-test/image')
            self.assertEqual((Path(directory) / 'openai-image-test.png').read_bytes(), image.content)

    def test_tavern_model_discovery_with_key_and_cors(self):
        self.login('admin@example.com', 'long-test-password')
        account = self.admin_post('/api/admin/upstreams', {
            'name': 'novelai', 'provider': 'novelai',
            'base_url': 'http://127.0.0.1:9999', 'api_key': 'upstream-secret',
        }).json()
        for public_name in ('nai-diffusion-4-5-full', 'tavern-anime'):
            created = self.admin_post('/api/admin/mappings', {
                'public_name': public_name, 'upstream_account_id': account['id'],
                'upstream_model': 'nai-diffusion-4-5-full', 'price': '0.1000',
            })
            self.assertEqual(created.status_code, 200, created.text)
        admin_id = self.client.get('/api/auth/me').json()['id']
        issued = self.admin_post(f'/api/admin/users/{admin_id}/keys', {'name': 'tavern'}).json()
        self.assertTrue(issued['key'].startswith('pst-'))
        path = '/genarate/v1/models'
        self.assertEqual(self.client.get(path).status_code, 401)
        response = self.client.get(path, headers={'Authorization': 'Bearer ' + issued['key']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'object': 'list', 'data': [
            {'id': name, 'object': 'model', 'owned_by': 'novelaipay'}
            for name in ('nai-diffusion-4-5-full', 'tavern-anime')]})
        preflight = self.client.options(path, headers={
            'Origin': 'http://127.0.0.1:8009',
            'Access-Control-Request-Method': 'GET',
            'Access-Control-Request-Headers': 'authorization',
        })
        self.assertEqual(preflight.status_code, 200, preflight.text)
        self.assertEqual(preflight.headers['access-control-allow-origin'], 'http://127.0.0.1:8009')
        self.assertEqual(self.client.get('/genarate/unknown').status_code, 404)

    def test_novelai_proxy_returns_zip_and_charges_actual_anlas(self):
        self.login('admin@example.com', 'long-test-password')
        account = self.admin_post('/api/admin/upstreams', {
            'name': 'novelai', 'provider': 'novelai',
            'base_url': 'https://image.novelai.net', 'api_key': 'upstream-secret',
        }).json()
        self.assertEqual(self.admin_post('/api/admin/mappings', {
            'public_name': 'anime', 'upstream_account_id': account['id'],
            'upstream_model': 'nai-diffusion-4-5-full', 'price': '0.1000',
        }).status_code, 200)
        admin_id = self.client.get('/api/auth/me').json()['id']
        self.assertEqual(self.admin_post('/api/admin/credit', {
            'user_id': admin_id, 'amount': '10', 'reference': 'proxy-test',
        }).status_code, 200)
        key = self.admin_post(f'/api/admin/users/{admin_id}/keys', {'name': 'nai-proxy'}).json()['key']
        headers = {'Authorization': 'Bearer ' + key}
        payload = {'action': 'generate', 'model': 'nai-diffusion-4-5-full',
                   'input': 'a red kite', 'parameters': {
                       'width': 1024, 'height': 1024, 'steps': 23,
                       'negative_prompt': 'clouds', 'sm': True,
                       'dynamic_thresholding': True, 'n_samples': 1,
                       'v4_prompt': {'caption': {'base_caption': 'a red kite',
                           'char_captions': [{'char_caption': 'red coat',
                                              'centers': [{'x': 0.2, 'y': 0.8}]}]}},
                       'v4_negative_prompt': {'caption': {'base_caption': 'clouds',
                           'char_captions': [{'char_caption': 'hat'}]}},
                   }}
        self.assertEqual(self.client.post('/ai/generate-image', json={
            **payload, 'action': 'img2img'}, headers=headers).status_code, 422)
        self.assertEqual(self.client.post('/ai/generate-image', json={
            **payload, 'parameters': {**payload['parameters'], 'n_samples': 2}},
            headers=headers).status_code, 422)
        archive_bytes = io.BytesIO()
        image = b'\x89PNG\r\n\x1a\nimage'
        with zipfile.ZipFile(archive_bytes, 'w') as archive:
            archive.writestr('image_0.png', image)
        generation_request = httpx.Request('POST', 'https://image.novelai.net/ai/generate-image')
        generation_response = httpx.Response(200, content=archive_bytes.getvalue(),
                                             request=generation_request)
        balance_request = httpx.Request('GET', 'https://image.novelai.net/user/subscription')
        balances = [httpx.Response(200, json={'trainingStepsLeft': {
            'fixedTrainingStepsLeft': value, 'purchasedTrainingSteps': 0}}, request=balance_request)
                    for value in (100, 60)]
        with tempfile.TemporaryDirectory() as directory:
            with patch('app.upstream.IMAGE_DIR', Path(directory)), \
                 patch('app.api.user.IMAGE_DIR', Path(directory)), \
                 patch('app.upstream.httpx.get', side_effect=balances) as balance, \
                 patch('app.upstream.httpx.post', return_value=generation_response) as send:
                result = self.client.post('/ai/generate-image', json=payload, headers=headers)
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.headers['content-type'], 'application/zip')
                with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
                    self.assertEqual(archive.read('image_0.png'), image)
                sent = send.call_args.kwargs['json']
                self.assertEqual(sent['parameters']['width'], 1024)
                self.assertEqual(sent['parameters']['sm'], False)
                self.assertEqual(sent['parameters']['dynamic_thresholding'], True)
                self.assertEqual(sent['parameters']['v4_prompt']['caption']['char_captions'][0],
                                 {'char_caption': 'red coat', 'centers': [{'x': 0.2, 'y': 0.8}]})
                self.assertEqual(sent['parameters']['v4_negative_prompt']['caption']['char_captions'][0]
                                 ['char_caption'], 'hat')
                self.assertEqual(balance.call_args.args[0], 'https://image.novelai.net/user/subscription')
        self.assertEqual(self.client.get('/api/billing').json()['balance'], '5.9000')
        self.assertEqual(self.client.get('/api/billing').json()['reserved'], '0.0000')

    def test_tavern_nai_proxy_shape_returns_accessible_image(self):
        self.login('admin@example.com', 'long-test-password')
        account = self.admin_post('/api/admin/upstreams', {
            'name': 'novelai', 'provider': 'novelai',
            'base_url': 'http://127.0.0.1:9999', 'api_key': 'upstream-secret',
        }).json()
        self.assertEqual(self.admin_post('/api/admin/mappings', {
            'public_name': 'nai-diffusion-4-5-full', 'upstream_account_id': account['id'],
            'upstream_model': 'nai-diffusion-4-5-full', 'price': '0.1000',
        }).status_code, 200)
        admin_id = self.client.get('/api/auth/me').json()['id']
        self.assertEqual(self.admin_post('/api/admin/credit', {
            'user_id': admin_id, 'amount': '10', 'reference': 'tavern-proxy',
        }).status_code, 200)
        key = self.admin_post(f'/api/admin/users/{admin_id}/keys', {'name': 'tavern'}).json()['key']
        body = {'model': 'nai-diffusion-4-5-full', 'tag': 'a red kite',
                'negative': 'clouds', 'size': '横图', 'steps': '20',
                'scale': '7', 'cfg': '0', 'stream': 1, 'seed': -1}
        self.assertEqual(self.client.post('/genarate', json={
            **body, 'addition': {'imageBase64': 'encoded-image'}},
            headers={'Authorization': 'Bearer ' + key}).status_code, 422)
        with tempfile.TemporaryDirectory() as directory:
            def generated(job):
                (Path(directory) / f'{job.id}.png').write_bytes(b'\x89PNG\r\n\x1a\nimage')
                return {'data': [{'url': f'/api/jobs/{job.id}/image'}], 'anlas_charged': 12}

            with patch('app.api.user.IMAGE_DIR', Path(directory)), \
                 patch('app.worker.NovelAIImageAdapter.generate', side_effect=generated):
                response = self.client.post('/genarate', json=body,
                                            headers={'Authorization': 'Bearer ' + key})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertLess(abs(response.json()['created'] - time.time()), 30)
                image_url = response.json()['url']
                self.assertEqual(response.json()['data'][0]['url'], image_url)
                self.assertEqual(self.client.get(image_url).status_code, 200)
                self.assertEqual(self.client.get(image_url.replace('token=', 'token=bad')).status_code, 404)
                job = self.client.get('/v1/jobs/' + response.json()['job_id'],
                                      headers={'Authorization': 'Bearer ' + key}).json()
                self.assertEqual(job['size'], '1216x832')
                self.assertEqual(job['parameters']['negative_prompt'], 'clouds')
                self.assertEqual(job['amount'], '1.3000')

    def test_img2img_plugin_mapping_and_zero_anlas_surcharge(self):
        self.login('admin@example.com', 'long-test-password')
        account = self.admin_post('/api/admin/upstreams', {
            'name': 'novelai', 'provider': 'novelai',
            'base_url': 'http://127.0.0.1:9999', 'api_key': 'upstream-secret',
            'opus_free': True,
        }).json()
        self.assertEqual(self.admin_post('/api/admin/mappings', {
            'public_name': 'nai-diffusion-4-5-full', 'upstream_account_id': account['id'],
            'upstream_model': 'nai-diffusion-4-5-full', 'price': '0.1000',
            'extra_amount': '0.1000',
        }).status_code, 200)
        admin_id = self.client.get('/api/auth/me').json()['id']
        self.admin_post('/api/admin/credit', {'user_id': admin_id, 'amount': '1', 'reference': 'img2img'})
        key = self.admin_post(f'/api/admin/users/{admin_id}/keys', {'name': 'img2img'}).json()['key']
        input_image = io.BytesIO()
        Image.new('RGB', (16, 16), 'red').save(input_image, format='PNG')
        source = base64.b64encode(input_image.getvalue()).decode()
        body = {'model': 'nai-diffusion-4-5-full', 'tag': 'a red kite',
                'addition': {'imageToImageBase64': source, 'i2iforce': '0.65',
                             'i2icl': '0.1', 'vibeTransferList': [{
                                 'base64': source, 'infoExtract': 0.8, 'refStrength': 0.4}]}}
        model, prompt, size, params = normalize_request(body)
        self.assertEqual(params.action, 'img2img')
        self.assertEqual(params.strength, 0.65)
        self.assertEqual(params.references[0].strength, 0.4)
        _, _, _, roles = normalize_request({'model': model, 'tag': prompt,
            'addition': {'multiRoleList': [
                {'prompt': 'red coat', 'uc': 'hat', 'center': {'x': 0.2, 'y': 0.8}},
                {'tags': ['blue scarf'], 'position': 'C3'},
            ]}})
        self.assertEqual(roles.character_prompts[0].negative_prompt, 'hat')
        self.assertEqual(roles.character_prompts[0].top, 0.8)
        self.assertEqual(roles.character_prompts[1].prompt, 'blue scarf')
        _, _, _, variety = normalize_request({'model': model, 'tag': prompt,
                                               'variety_boost': True, 'decrisper': True})
        self.assertTrue(variety.dynamic_thresholding)
        self.assertAlmostEqual(generation_payload(model, prompt, size, variety)['parameters']
                               ['skip_cfg_above_sigma'], (1024 * 1024 / 1011712) ** 0.5 * 58)
        self.assertEqual(generation_payload(model, prompt, size, roles)['parameters']
                         ['v4_prompt']['caption']['char_captions'][0]['centers'],
                         [{'x': 0.2, 'y': 0.8}])
        with tempfile.TemporaryDirectory() as directory:
            with patch('app.novelai.INPUT_DIR', Path(directory)):
                submitted = self.client.post('/v1/images/generations', json={
                    'model': model, 'prompt': prompt, 'size': size,
                    'parameters': params.model_dump()}, headers={
                        'Authorization': 'Bearer ' + key, 'Idempotency-Key': 'img2img-zero'})
                self.assertEqual(submitted.status_code, 202, submitted.text)
                self.assertEqual(submitted.json()['amount'], '0.5000')
                self.assertNotIn(source, json.dumps(submitted.json()))
                with db.SessionLocal() as session:
                    job = session.get(GenerationJob, submitted.json()['id'])
                    upstream = generation_payload(job.upstream_model, job.prompt, job.size,
                                                  type(params).model_validate(job.parameters))
                    self.assertEqual(upstream['action'], 'img2img')
                    self.assertEqual(upstream['parameters']['image'], source)
                    self.assertEqual(upstream['parameters']['reference_image_multiple'], [source])
                    asset = job.parameters['image']
                    infill = generation_payload(job.upstream_model, job.prompt, job.size,
                        ImageParameters(action='infill', image=asset, mask=asset,
                                        inpaint_img2img_strength=0.5))
                    self.assertEqual(infill['model'], 'nai-diffusion-4-5-full-inpainting')
                    self.assertEqual(infill['parameters']['img2img']['strength'], 0.5)
                    character = generation_payload(job.upstream_model, job.prompt, job.size,
                        ImageParameters(precise_reference={'image': asset}))
                    self.assertEqual(character['parameters']['director_reference_descriptions'][0]
                                     ['caption']['base_caption'], 'character&style')
                    self.assertEqual(character['parameters']['director_reference_secondary_strength_values'], [1])
                    with Image.open(io.BytesIO(base64.b64decode(
                            character['parameters']['director_reference_images'][0]))) as reference:
                        self.assertEqual(reference.size, (1472, 1472))
                archive_bytes = io.BytesIO()
                with zipfile.ZipFile(archive_bytes, 'w') as archive:
                    archive.writestr('image_0.png', b'\x89PNG\r\n\x1a\nimage')
                balance_request = httpx.Request('GET', 'http://127.0.0.1:9999/user/subscription')
                balances = [httpx.Response(200, json={'trainingStepsLeft': {
                    'fixedTrainingStepsLeft': 100, 'purchasedTrainingSteps': 0}},
                    request=balance_request) for _ in range(2)]
                encoded = httpx.Response(200, content=b'vibe-token', request=httpx.Request(
                    'POST', 'http://127.0.0.1:9999/ai/encode-vibe'))
                generated = httpx.Response(200, content=archive_bytes.getvalue(), request=httpx.Request(
                    'POST', 'http://127.0.0.1:9999/ai/generate-image'))
                with patch('app.upstream.IMAGE_DIR', Path(directory)), \
                     patch('app.upstream.httpx.get', side_effect=balances), \
                     patch('app.upstream.httpx.post', side_effect=[encoded, generated]) as send:
                    self.assertTrue(run_once())
                    self.assertEqual(send.call_args_list[0].kwargs['json']['information_extracted'], 0.8)
                    generation = send.call_args_list[1].kwargs['json']
                    self.assertEqual(generation['parameters']['reference_image_multiple'],
                                     [base64.b64encode(b'vibe-token').decode()])
                    self.assertNotIn('reference_information_extracted_multiple', generation['parameters'])
                job = self.client.get('/v1/jobs/' + submitted.json()['id'], headers={
                    'Authorization': 'Bearer ' + key}).json()
                self.assertEqual(job['amount'], '0.1000')
                self.assertEqual(job['anlas_cost'], 0)
                self.assertEqual(self.client.get('/api/billing').json()['balance'], '0.9000')
                failed = self.client.post('/v1/images/generations', json={
                    'model': model, 'prompt': prompt, 'size': size,
                    'parameters': params.model_dump()}, headers={
                        'Authorization': 'Bearer ' + key, 'Idempotency-Key': 'img2img-failed'})
                self.assertEqual(failed.status_code, 202, failed.text)
                with patch('app.worker.NovelAIImageAdapter.generate', side_effect=ValueError('upstream rejected')):
                    self.assertTrue(run_once())
                self.assertEqual(self.client.get('/api/billing').json()['balance'], '0.9000')
                self.assertEqual(self.client.get('/api/billing').json()['reserved'], '0.0000')

    def test_end_to_end_balance_idempotency_payment_and_recovery(self):
        self.login('admin@example.com', 'long-test-password')
        upstream = self.admin_post('/api/admin/upstreams', {
            'name': 'test', 'base_url': 'http://127.0.0.1:9999/v1', 'api_key': 'super-secret-upstream',
        })
        self.assertEqual(upstream.status_code, 200, upstream.text)
        mapping = self.admin_post('/api/admin/mappings', {
            'public_name': 'illustration-pro', 'upstream_account_id': upstream.json()['id'],
            'upstream_model': 'test-image', 'price': '3.0000', 'max_concurrency': 3,
        })
        self.assertEqual(mapping.status_code, 200, mapping.text)
        user = self.admin_post('/api/admin/users', {'name': 'Image User', 'email': 'user@example.com',
                                                    'password': 'user-long-password'})
        self.assertEqual(user.status_code, 200, user.text)
        user_id = user.json()['id']
        self.assertEqual(self.admin_post('/api/admin/credit', {
            'user_id': user_id, 'amount': '5.0000', 'reference': 'opening',
        }).status_code, 200)
        with db.SessionLocal() as session:
            self.assertNotIn('super-secret-upstream', session.scalar(select(UpstreamAccount)).encrypted_key)

        self.client.cookies.clear()
        self.login('user@example.com', 'user-long-password')
        key_response = self.client.post('/api/keys', json={'name': 'test'},
                                        headers={'X-CSRF-Token': self.client.cookies['nvp_csrf']})
        self.assertEqual(key_response.status_code, 200, key_response.text)
        key = key_response.json()['key']
        headers = {'Authorization': 'Bearer ' + key, 'Idempotency-Key': 'request-1'}
        payload = {'model': 'illustration-pro', 'prompt': 'A mountain', 'size': '1024x1024'}
        first = self.client.post('/v1/images/generations', json=payload, headers=headers)
        self.assertEqual(first.status_code, 202, first.text)
        self.assertEqual(self.client.post('/v1/images/generations', json=payload, headers=headers).json()['id'], first.json()['id'])
        self.assertEqual(self.client.post('/v1/images/generations', json={**payload, 'prompt': 'Changed'}, headers=headers).status_code, 409)
        self.assertEqual(self.client.post('/v1/images/generations', json=payload,
                                          headers={**headers, 'Idempotency-Key': 'request-2'}).status_code, 402)

        with patch('app.worker.OpenAIImageAdapter.generate', return_value={'data': [{'url': 'https://example.com/image.png'}]}):
            self.assertTrue(run_once())
        self.assertEqual(self.client.get('/v1/jobs/' + first.json()['id'],
                                         headers={'Authorization': 'Bearer ' + key}).json()['status'], 'succeeded')
        billing = self.client.get('/api/billing').json()
        self.assertEqual(billing['balance'], '2.0000')
        self.assertEqual(billing['reserved'], '0.0000')
        self.assertEqual(len(billing['usage']), 1)
        consumption_csv = self.client.get('/api/billing/consumption/export')
        self.assertEqual(consumption_csv.status_code, 200, consumption_csv.text)
        self.assertIn(first.json()['id'], consumption_csv.text)
        self.assertEqual(len(list(csv.reader(io.StringIO(consumption_csv.content.decode('utf-8-sig'))))), 2)
        self.assertEqual(len(list(csv.reader(io.StringIO(self.client.get(
            '/api/billing/consumption/export?ids=999').content.decode('utf-8-sig'))))), 1)

        body = json.dumps({'provider': 'test', 'transaction_id': 'tx-1',
                           'user_id': user_id, 'amount': '10.0000'}).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(b'test-payment-secret', timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
        pay_headers = {'X-Novelaipay-Timestamp': timestamp, 'X-Novelaipay-Signature': signature,
                       'Content-Type': 'application/json'}
        paid = self.client.post('/api/payments/webhook', content=body, headers=pay_headers)
        self.assertEqual(paid.json(), {'accepted': True, 'credited': True})
        duplicate = self.client.post('/api/payments/webhook', content=body, headers=pay_headers)
        self.assertEqual(duplicate.json(), {'accepted': True, 'credited': False})
        self.assertEqual(self.client.get('/api/billing').json()['balance'], '12.0000')

        failed = self.client.post('/v1/images/generations', json=payload,
                                  headers={**headers, 'Idempotency-Key': 'request-3'})
        self.assertEqual(failed.status_code, 202, failed.text)
        with patch('app.worker.OpenAIImageAdapter.generate', side_effect=ValueError('invalid response')):
            self.assertTrue(run_once())
        failed_job = self.client.get('/v1/jobs/' + failed.json()['id'],
                                     headers={'Authorization': 'Bearer ' + key}).json()
        self.assertEqual(failed_job['status'], 'failed')
        self.assertEqual(failed_job['amount'], '0.0000')
        self.assertEqual(self.client.get('/api/billing').json()['balance'], '12.0000')

        pending = self.client.post('/v1/images/generations', json=payload,
                                   headers={**headers, 'Idempotency-Key': 'request-4'})
        self.assertEqual(pending.status_code, 202, pending.text)
        with db.SessionLocal() as session:
            job = claim_job(session, 180)
            self.assertEqual(job.id, pending.json()['id'])
            with session.begin():
                job.lease_until = utcnow() - timedelta(seconds=1)
            self.assertEqual(recover_expired(session), 1)
            self.assertEqual(session.get(GenerationJob, job.id).status, JobStatus.UNCERTAIN)
        self.client.cookies.clear()
        self.login('admin@example.com', 'long-test-password')
        resolution = self.admin_post('/api/admin/uncertain/' + pending.json()['id'] + '/resolve',
                                     {'succeeded': False, 'note': 'No upstream result'})
        self.assertEqual(resolution.status_code, 200, resolution.text)
        with db.SessionLocal() as session:
            self.assertEqual(session.get(User, user_id).reserved, 0)


if __name__ == '__main__':
    unittest.main()
