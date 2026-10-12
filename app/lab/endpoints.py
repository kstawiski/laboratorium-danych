"""Odkrywanie modeli; cache obejmuje wyłącznie publiczną listę Ollama."""
from collections import OrderedDict
import json
import threading
import time
from urllib.parse import urlsplit
import httpx
from .config import ModelConfig

_CACHE = OrderedDict()
_LOCK = threading.Lock()
TTL = 30.0


def endpoint_url(value):
    value = value.strip().rstrip('/')
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError('Podaj poprawny adres HTTP lub HTTPS i numer portu.') from None
    if len(value) > 2048 or parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Podaj adres HTTP lub HTTPS bez klucza, danych logowania i parametrów URL.')
    return value if parsed.path.strip('/') else value + '/v1'


def endpoint_models(base_url, api_key='', *, trust_env=True):
    url = endpoint_url(base_url)
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False, trust_env=trust_env) as client:
            response = client.get(url + '/models', headers={'Authorization': 'Bearer ' + api_key} if api_key else {})
            response.raise_for_status()
            names = response.json()['data']
            return list(dict.fromkeys(row['id'] for row in names if isinstance(row.get('id'), str) and row['id']))
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError('Nie można pobrać listy modeli. Sprawdź adres, dostępność serwera i klucz.') from None


def ollama_models(base_url):
    root = endpoint_url(base_url).removesuffix('/v1')
    with _LOCK:
        cached = _CACHE.get(root)
        if cached and time.monotonic() - cached[0] < TTL:
            return cached[1], cached[2]
    names, sizes, note = [], {}, None
    try:
        with httpx.Client(timeout=3.0, follow_redirects=False, trust_env=False) as client:
            response = client.get(root + '/api/tags')
            response.raise_for_status()
            rows = response.json()['models']
            sizes = {row.get('name'): row.get('size', 0) for row in rows}
            names = list(dict.fromkeys(row['name'] for row in rows
                                       if isinstance(row.get('name'), str) and row['name']))
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        try:
            names = endpoint_models(root + '/v1', trust_env=False)
        except ValueError:
            note = 'Ollama jest niedostępna. Możesz korzystać z pozostałych modeli.'
    configs = {f'Ollama: {name}': ModelConfig(f'Ollama: {name}', name, root, '', timeout=600, concurrency=1, per_server_concurrency=1,
                                                   transport='ollama', download_size=sizes.get(name, 0)) for name in names}
    with _LOCK:
        _CACHE[root] = (time.monotonic(), configs, note)
        while len(_CACHE) > 32:
            _CACHE.popitem(last=False)
    return configs, note


def refresh_ollama(base_url):
    root = endpoint_url(base_url).removesuffix('/v1')
    with _LOCK:
        _CACHE.pop(root, None)


def pull_model(base_url, name, on_progress):
    """NDJSON z natywnego /api/pull; nie wyświetla surowych błędów serwera."""
    root = endpoint_url(base_url).removesuffix('/v1')
    try:
        with httpx.Client(timeout=600.0, follow_redirects=False, trust_env=False) as client:
            with client.stream('POST', root + '/api/pull', json={'model': name, 'stream': True}) as response:
                response.raise_for_status()
                layers, totals = {}, {}
                success = False
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if item.get('error'):
                        raise ValueError
                    digest = item.get('digest', 'download')
                    if 'total' in item:
                        totals[digest] = max(0, int(item['total']))
                        layers[digest] = max(layers.get(digest, 0), int(item.get('completed', 0)))
                    success = item.get('status') == 'success'
                    total = sum(totals.values())
                    completed = sum(min(layers.get(d, 0), n) for d, n in totals.items())
                    on_progress(1.0 if success else min(completed / total, 1.0) if total else 0.0, completed, total)
                if not success:
                    raise ValueError
        refresh_ollama(root)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise ValueError('Nie udało się pobrać modelu. Sprawdź połączenie z internetem, wolne miejsce na dysku i czy Ollama jest uruchomiona. Spróbuj ponownie.') from None
