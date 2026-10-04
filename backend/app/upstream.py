import httpx

from .models import GenerationJob, UpstreamAccount
from .security import decrypt_upstream_key


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
