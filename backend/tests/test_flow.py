import hashlib
import hmac
import json
import os
import time
import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

os.environ.update({
    'APP_SECRET_KEY': 'test-session-secret-with-enough-length',
    'UPSTREAM_KEY_ENCRYPTION_KEY': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
    'PAYMENT_WEBHOOK_SECRET': 'test-payment-secret',
    'DATABASE_URL': 'sqlite://',
    'COOKIE_SECURE': 'false',
})

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.models import Base, GenerationJob, JobStatus, UpstreamAccount, utcnow
from app.security import hash_password
from app.models import User
from app.services import claim_job, recover_expired
from app.worker import run_once


class FlowTest(unittest.TestCase):
    def setUp(self):
        db.engine.dispose()
        db.engine = create_engine('sqlite://', poolclass=StaticPool,
                                  connect_args={'check_same_thread': False})
        db.SessionLocal.configure(bind=db.engine)
        Base.metadata.create_all(db.engine)
        with db.SessionLocal.begin() as session:
            session.add(User(email='admin@example.com', password_hash=hash_password('long-test-password'), is_admin=True))
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
        user = self.admin_post('/api/admin/users', {'email': 'user@example.com', 'password': 'user-long-password'})
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
        self.assertEqual(self.client.get('/v1/jobs/' + failed.json()['id'],
                                         headers={'Authorization': 'Bearer ' + key}).json()['status'], 'failed')
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
