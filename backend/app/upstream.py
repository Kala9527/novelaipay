import httpx
import base64
import io
import zipfile
from pathlib import Path

from .models import GenerationJob, UpstreamAccount
from .security import decrypt_upstream_key
from .novelai import ImageParameters, generation_payload
from .proxy import request as upstream_request


class UpstreamUncertain(Exception):
    pass


IMAGE_DIR = Path(__file__).resolve().parents[2] / 'data' / 'images'


def store_remote_image(job_id: str, image_url: str, timeout_seconds: int,
                       account: UpstreamAccount | None = None) -> Path:
    try:
        options = {'timeout': timeout_seconds, 'follow_redirects': True}
        response = (upstream_request(account, 'GET', image_url, **options) if account else
                    httpx.get(image_url, **options))
        response.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        raise UpstreamUncertain('Upstream image could not be retrieved; check before settlement') from exc
    image = response.content
    if len(image) > 20 * 1024 * 1024 or not image.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')):
        raise UpstreamUncertain('Upstream returned an invalid image')
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = IMAGE_DIR / f'{job_id}{".png" if image.startswith(b"\x89PNG") else ".jpg"}'
    path.write_bytes(image)
    return path


class OpenAIImageAdapter:
    def __init__(self, account: UpstreamAccount, timeout_seconds: int):
        self.account = account
        self.timeout_seconds = timeout_seconds

    def generate(self, job: GenerationJob) -> dict:
        url = self.account.base_url.rstrip('/') + '/images/generations'
        try:
            response = upstream_request(self.account, 'POST',
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
        store_remote_image(job.id, images[0]['url'], self.timeout_seconds, self.account)
        return {'data': [{'url': f'/api/jobs/{job.id}/image'}]}


class NovelAIImageAdapter:
    def __init__(self, account: UpstreamAccount, timeout_seconds: int):
        self.account = account
        self.timeout_seconds = timeout_seconds

    def balance(self) -> int:
        response = upstream_request(self.account, 'GET',
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
        parameters = payload['parameters']
        references = parameters.get('reference_image_multiple', [])
        if references:
            encoded = []
            for image, extraction in zip(references, parameters['reference_information_extracted_multiple']):
                raw = base64.b64decode(image)
                if not raw.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')):
                    encoded.append(image)
                    continue
                response = upstream_request(self.account, 'POST',
                    self.account.base_url.rstrip('/') + '/ai/encode-vibe',
                    headers={'Authorization': 'Bearer ' + decrypt_upstream_key(self.account.encrypted_key)},
                    json={'image': image, 'information_extracted': extraction,
                          'model': payload['model']}, timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                if not response.content or len(response.content) > 5 * 1024 * 1024:
                    raise ValueError('NovelAI returned an invalid Vibe token')
                encoded.append(base64.b64encode(response.content).decode('ascii'))
            parameters['reference_image_multiple'] = encoded
            parameters.pop('reference_information_extracted_multiple', None)
        try:
            response = upstream_request(self.account, 'POST',
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
