"""One controlled NovelAI generation through the local HTTP API.

Set NOVELAI_TOKEN in the environment; no credential is printed or persisted in
this script. Run from backend after migration, bootstrap, and starting port 8009.
"""

import os
import uuid
from pathlib import Path

import httpx
import yaml

from app.worker import run_once


def main() -> None:
    token = os.environ['NOVELAI_TOKEN']
    config = yaml.safe_load((Path(__file__).resolve().parents[2] / 'config.yaml').read_text(encoding='utf-8'))
    base = 'http://127.0.0.1:8009'
    name = 'live-' + uuid.uuid4().hex[:8]
    with httpx.Client(base_url=base, timeout=30) as client:
        auth = client.post('/api/auth/login', json={
            'email': config['admin']['email'], 'password': config['admin']['password'],
        })
        auth.raise_for_status()
        headers = {'X-CSRF-Token': client.cookies['nvp_csrf']}
        def post(path: str, payload: dict) -> dict:
            response = client.post(path, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

        account = post('/api/admin/upstreams', {
            'name': name, 'base_url': 'https://image.novelai.net',
            'api_key': token, 'provider': 'novelai', 'opus_free': True,
        })
        post('/api/admin/mappings', {
            'public_name': name, 'upstream_account_id': account['id'],
            'upstream_model': 'nai-diffusion-4-5-full', 'price': '0.1000',
        })
        key = post('/api/keys', {'name': name})['key']
        response = client.post('/v1/images/generations', json={
            'model': name, 'prompt': 'a red maple leaf on a clean white background',
            'size': '1024x1024', 'parameters': {'steps': 23, 'scale': 4,
                'sampler': 'k_euler_ancestral'},
        }, headers={'Authorization': 'Bearer ' + key, 'Idempotency-Key': name})
        response.raise_for_status()
        job_id = response.json()['id']
        print(f'submitted job={job_id}')
        if not run_once():
            raise RuntimeError('Worker did not claim the job')
        result = client.get(f'/v1/jobs/{job_id}', headers={'Authorization': 'Bearer ' + key})
        result.raise_for_status()
        job = result.json()
        print(f"status={job['status']} anlas={job['anlas_cost']} amount={job['amount']}")
        if job['status'] != 'succeeded':
            print(f"error={job['error']}")
            return
        image = client.get(job['result']['data'][0]['url'])
        image.raise_for_status()
        print(f'image_url={base}{job["result"]["data"][0]["url"]} bytes={len(image.content)}')


if __name__ == '__main__':
    main()
