"""Odkrywanie modeli; cache obejmuje wyłącznie publiczną listę Ollama."""
from collections import OrderedDict
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
        raise ValueError('Podaj poprawny adres HTTP lub HTTPS i numer portu.') from exc
    if len(value) > 2048 or parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Podaj adres HTTP lub HTTPS bez klucza, danych logowania i parametrów URL.')
    return value if parsed.path.strip('/') else value + '/v1'


def endpoint_models(base_url, api_key=''):
    url = endpoint_url(base_url)
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False) as client:
            response = client.get(url + '/models', headers={'Authorization': 'Bearer ' + api_key} if api_key else {})
            response.raise_for_status()
            names = response.json()['data']
            return list(dict.fromkeys(row['id'] for row in names if isinstance(row.get('id'), str) and row['id']))
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError('Nie można pobrać listy modeli. Sprawdź adres, dostępność serwera i klucz.') from exc


def ollama_models(base_url):
    root = endpoint_url(base_url).removesuffix('/v1')
    with _LOCK:
        cached = _CACHE.get(root)
        if cached and time.monotonic() - cached[0] < TTL:
            return cached[1], cached[2]
    names, note = [], None
    try:
        with httpx.Client(timeout=3.0, follow_redirects=False) as client:
            response = client.get(root + '/api/tags')
            response.raise_for_status()
            names = list(dict.fromkeys(row['name'] for row in response.json()['models']
                                       if isinstance(row.get('name'), str) and row['name']))
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        try:
            names = endpoint_models(root + '/v1')
        except ValueError:
            note = 'Ollama jest niedostępna. Możesz korzystać z pozostałych modeli.'
    configs = {f'Ollama: {name}': ModelConfig(f'Ollama: {name}', name, root + '/v1', '') for name in names}
    with _LOCK:
        _CACHE[root] = (time.monotonic(), configs, note)
        while len(_CACHE) > 32:
            _CACHE.popitem(last=False)
    return configs, note
