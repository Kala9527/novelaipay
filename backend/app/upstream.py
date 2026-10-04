import httpx
import io
import zipfile
from pathlib import Path

from .models import GenerationJob, UpstreamAccount
from .security import decrypt_upstream_key
from .novelai import ImageParameters, generation_payload


class UpstreamUncertain(Exception):
    pass


class OpenAIImageAdapter:
    def __init__(self, account: UpstreamAccount, timeout_seconds: int):
        self.account = account
        self.timeout_seconds = timeout_seconds

    def generate(self, job: GenerationJob) -> dict:
        url = self.account.base_url.rstrip('/') + '/images/generations'
        try:
            response = httpx.post(
                url,
                headers={'Authorization': 'Bearer ' + decrypt_upstream_key(self.account.encrypted_key)},
                json={'model': job.upstream_model, 'prompt': job.prompt, 'size': job.size,
                      'n': 1, 'response_format': 'url'},
                timeout=self.timeout_seconds,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise UpstreamUncertain(f'Upstream result unknown: {type(exc).__name__}') from exc
        if response.status_code >= 500:
            raise UpstreamUncertain(f'Upstream HTTP {response.status_code}; check before retrying')
        response.raise_for_status()
        data = response.json()
        images = data.get('data') if isinstance(data, dict) else None
        if not isinstance(images, list) or not images or not isinstance(images[0], dict) or not images[0].get('url'):
            raise UpstreamUncertain('Upstream returned no image URL; check response before settlement')
        return {'data': [{'url': image['url']} for image in images if isinstance(image, dict) and image.get('url')]}


IMAGE_DIR = Path(__file__).resolve().parents[2] / 'data' / 'images'


class NovelAIImageAdapter:
    def __init__(self, account: UpstreamAccount, timeout_seconds: int):
        self.account = account
        self.timeout_seconds = timeout_seconds

    def balance(self) -> int:
        response = httpx.get(
            self.account.base_url.rstrip('/') + '/user/subscription',
            headers={'Authorization': 'Bearer ' + decrypt_upstream_key(self.account.encrypted_key)},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        steps = response.json()['trainingStepsLeft']
        return int(steps['fixedTrainingStepsLeft']) + int(steps['purchasedTrainingSteps'])

    def generate(self, job: GenerationJob) -> dict:
        payload = generation_payload(job.upstream_model, job.prompt, job.size,
                                     ImageParameters.model_validate(job.parameters or {}))
        before = self.balance()
        try:
            response = httpx.post(
                self.account.base_url.rstrip('/') + '/ai/generate-image',
                headers={'Authorization': 'Bearer ' + decrypt_upstream_key(self.account.encrypted_key),
                         'Accept': 'application/zip'},
                json=payload, timeout=self.timeout_seconds,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise UpstreamUncertain(f'NovelAI result unknown: {type(exc).__name__}') from exc
        if response.status_code >= 500:
            raise UpstreamUncertain(f'NovelAI HTTP {response.status_code}; check before retrying')
        response.raise_for_status()
        if len(response.content) > 30 * 1024 * 1024:
            raise UpstreamUncertain('NovelAI image archive exceeds local limit')
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                candidates = [item for item in archive.infolist()
                              if item.filename.lower().endswith('.png') and not item.is_dir()]
                if len(candidates) != 1 or candidates[0].file_size > 20 * 1024 * 1024:
                    raise ValueError('Expected one PNG image in NovelAI archive')
                image = archive.read(candidates[0])
        except (zipfile.BadZipFile, RuntimeError, ValueError) as exc:
            raise UpstreamUncertain('NovelAI response archive could not be verified') from exc
        if not image.startswith(b'\x89PNG\r\n\x1a\n'):
            raise UpstreamUncertain('NovelAI returned invalid PNG data')
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        (IMAGE_DIR / f'{job.id}.png').write_bytes(image)
        try:
            after = self.balance()
        except Exception as exc:
            raise UpstreamUncertain('Image received but NovelAI balance could not be checked') from exc
        charged = before - after
        if charged < 0:
            raise UpstreamUncertain('NovelAI balance increased during generation; reconcile manually')
        return {'data': [{'url': f'/api/jobs/{job.id}/image'}], 'anlas_charged': charged}
