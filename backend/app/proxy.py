from urllib.parse import urlsplit

import httpx

from .models import UpstreamAccount
from .security import decrypt_upstream_key


def validate_proxy_url(value: str) -> str:
    value = value.strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError('Invalid proxy URL') from exc
    if (parsed.scheme not in ('http', 'https', 'socks5', 'socks5h') or
            not parsed.hostname or port is None or not 1 <= port <= 65535 or
            parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('Use an HTTP, HTTPS or SOCKS5 proxy URL with host and port')
    return value


def proxy_label(value: str) -> str:
    parsed = urlsplit(value)
    host = parsed.hostname or ''
    if ':' in host:
        host = f'[{host}]'
    return f'{parsed.scheme}://{host}:{parsed.port}'


def request(account: UpstreamAccount, method: str, url: str, **kwargs) -> httpx.Response:
    if account.proxy_id is None:
        return getattr(httpx, method.lower())(url, **kwargs)
    if account.proxy is None:
        raise ValueError('Assigned proxy no longer exists')
    proxy_url = decrypt_upstream_key(account.proxy.encrypted_url)
    with httpx.Client(proxy=proxy_url, trust_env=False) as client:
        return client.request(method, url, **kwargs)
