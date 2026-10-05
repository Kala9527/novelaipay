"""Run real NovelAI feature calls against the local server and verify billing.

Run with the project's activated Conda environment and an already running
start.ps1. Calls use the configured administrator and an existing API key.
"""

import base64
import io
import os
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path

import httpx
import yaml
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.db import SessionLocal
from app.models import UpstreamAccount
from app.upstream import NovelAIImageAdapter


BASE = os.environ.get('LIVE_BASE_URL', 'http://127.0.0.1:8009')


def image_inputs() -> tuple[str, str]:
    images = sorted((ROOT / 'data' / 'images').glob('*.png'))
    if not images:
        raise RuntimeError('A PNG in data/images is required for image input tests')
    with Image.open(images[-1]) as source:
        image = source.convert('RGB').resize((1024, 1024))
    original = io.BytesIO()
    image.save(original, format='PNG')
    mask = Image.new('L', image.size, 0)
    ImageDraw.Draw(mask).ellipse((256, 256, 768, 768), fill=255)
    masked = io.BytesIO()
    mask.save(masked, format='PNG')
    return base64.b64encode(original.getvalue()).decode(), base64.b64encode(masked.getvalue()).decode()


def main() -> None:
    config = yaml.safe_load((ROOT / 'config.yaml').read_text(encoding='utf-8'))
    original, mask = image_inputs()
    with httpx.Client(base_url=BASE, timeout=30) as client:
        login = client.post('/api/auth/login', json={
            'email': config['admin']['email'], 'password': config['admin']['password'],
        })
        login.raise_for_status()
        headers = {'X-CSRF-Token': client.cookies['nvp_csrf']}
        models = client.get('/api/models', headers=headers).json()
        model = next((row for row in models if row['name'] == os.environ.get('LIVE_MODEL', 'nai-diffusion-4-5-full')), None)
        if model is None or model['billing_mode'] != 'anlas' or Decimal(model['extra_amount']) != Decimal('0.1'):
            raise RuntimeError('Expected an enabled NovelAI model with a 0.10 surcharge')
        mappings = client.get('/api/admin/mappings', headers=headers).json()
        mapping = next(row for row in mappings if row['public_name'] == model['name'])
        with SessionLocal() as session:
            account = session.get(UpstreamAccount, mapping['upstream_account_id'])
            adapter = NovelAIImageAdapter(account, 30)
        keys = client.get('/api/keys', headers=headers).json()
        if not keys:
            raise RuntimeError('Create an administrator API key before the live test')
        key_response = client.get(f"/api/keys/{keys[0]['id']}/secret", headers=headers)
        key_response.raise_for_status()
        authorization = {'Authorization': 'Bearer ' + key_response.json()['key']}

        cases = [
            ('text', {}),
            ('img2img', {'action': 'img2img', 'image': original, 'strength': 0.65, 'noise': 0.05}),
            ('infill', {'action': 'infill', 'image': original, 'mask': mask,
                        'strength': 0.7, 'inpaint_img2img_strength': 1}),
            ('vibe', {'references': [{'image': original, 'strength': 0.6,
                                     'information_extracted': 1}]}),
            ('precise', {'precise_reference': {'image': original, 'strength': 1,
                                              'fidelity': 1, 'description': 'character&style'}}),
            ('characters', {'character_prompts': [{'prompt': 'blue jacket',
                                                   'negative_prompt': 'red jacket',
                                                   'center': 0.35, 'top': 0.5}]}),
            ('quality', {'quality_toggle': True}),
            ('smea', {'smea': True}),
            ('smea_dyn', {'smea': True, 'smea_dyn': True}),
            ('dynamic', {'dynamic_thresholding': True}),
            ('cfg', {'cfg_rescale': 0.15}),
            ('seed', {'seed': 42}),
            ('advanced', {'quality_toggle': True, 'smea': True, 'smea_dyn': True,
                          'dynamic_thresholding': True, 'cfg_rescale': 0.15, 'seed': 42}),
        ]
        selected = set(filter(None, os.environ.get('LIVE_CASES', '').split(',')))
        for name, feature in cases:
            if selected and name not in selected:
                continue
            before = client.get('/api/billing', headers=headers).json()
            upstream_before = adapter.balance()
            request_headers = {**authorization, 'Idempotency-Key': f'live-{name}-{uuid.uuid4().hex}'}
            response = client.post('/v1/images/generations', headers=request_headers, json={
                'model': model['name'], 'prompt': 'a blue-haired explorer in a sunlit garden, anime illustration',
                'size': '1024x1024', 'parameters': {'steps': 23, 'scale': 4,
                    'sampler': 'k_euler_ancestral', 'negative_prompt': 'blur, watermark', **feature},
            })
            print(f'{name}: submit={response.status_code}', flush=True)
            response.raise_for_status()
            job_id = response.json()['id']
            deadline = time.monotonic() + 240
            while True:
                job_response = client.get(f'/v1/jobs/{job_id}', headers=authorization)
                job_response.raise_for_status()
                job = job_response.json()
                if job['status'] not in ('queued', 'running') or time.monotonic() >= deadline:
                    break
                time.sleep(3)
            after = client.get('/api/billing', headers=headers).json()
            upstream_after = adapter.balance()
            amount = Decimal(job['amount'])
            balance_change = Decimal(before['balance']) - Decimal(after['balance'])
            usage = [row for row in after['usage'] if row['job_id'] == job_id]
            print(f"{name}: status={job['status']} anlas={job['anlas_cost']} upstream_change={upstream_before - upstream_after} amount={amount} balance_change={balance_change} usage={len(usage)} error={job['error']}", flush=True)
            if job['status'] == 'succeeded':
                expected = Decimal(model['price']) * job['anlas_cost'] + Decimal('0.1')
                assert amount == expected == balance_change, f'{name}: charge mismatch'
                assert upstream_before - upstream_after == job['anlas_cost'], f'{name}: upstream charge mismatch'
                assert len(usage) == 1 and Decimal(usage[0]['amount']) == amount
                image_response = client.get(job['result']['data'][0]['url'])
                image_response.raise_for_status()
                assert image_response.content.startswith(b'\x89PNG\r\n\x1a\n')
                print(f'{name}: image_bytes={len(image_response.content)}', flush=True)
            elif job['status'] == 'failed':
                assert balance_change == 0 and not usage and Decimal(after['reserved']) == Decimal(before['reserved'])
                assert upstream_before == upstream_after
            elif job['status'] == 'uncertain' and upstream_before == upstream_after:
                resolution = client.post(f'/api/admin/uncertain/{job_id}/resolve',
                                         headers=headers, json={'succeeded': False,
                                         'note': '上游 HTTP 500；调用前后 Anlas 余额未变化'})
                resolution.raise_for_status()
                print(f'{name}: released unchanged upstream balance', flush=True)
            else:
                raise RuntimeError(f'{name}: task remains {job["status"]}; inspect before any retry')


if __name__ == '__main__':
    main()
