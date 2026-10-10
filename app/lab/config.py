from dataclasses import dataclass
from pathlib import Path
import os

APP_DIR = Path(__file__).resolve().parent.parent

@dataclass(frozen=True)
class ModelConfig:
    label: str
    model: str
    base_url: str
    api_key: str
    timeout: float = 180.0
    concurrency: int = 6
    base_urls: tuple[str, ...] = ()
    per_server_concurrency: int = 4

    @property
    def servers(self):
        return self.base_urls or (self.base_url,)


def secret(name: str) -> str:
    value = os.getenv(name)
    if value is not None:
        return value.strip()
    path = os.getenv(name + '_FILE')
    return Path(path).read_text(encoding='utf-8').strip() if path else ''


def model_configs() -> dict[str, ModelConfig]:
    base = os.getenv('ORNITH_BASE_URL', 'http://localhost:11434/v1').rstrip('/')
    urls = tuple(dict.fromkeys(u.strip().rstrip('/') for u in os.getenv('ORNITH_BASE_URLS', '').split(',') if u.strip()))
    limit = int(os.getenv('ORNITH_MAX_CONCURRENCY_PER_SERVER', '4'))
    if limit < 1:
        raise ValueError('Limit na serwer musi być dodatni.')
    return {
        'Ornith': ModelConfig('Ornith', os.getenv('ORNITH_MODEL', 'ornith-1.5-9b'),
                              urls[0] if urls else base, secret('ORNITH_API_KEY'),
                              base_urls=urls, per_server_concurrency=limit),
        'Qwen': ModelConfig('Qwen', os.getenv('QWEN_MODEL', 'umed-qwen'),
                            os.getenv('QWEN_BASE_URL', 'http://localhost:4000/v1').rstrip('/'),
                            secret('QWEN_API_KEY'), per_server_concurrency=6),
    }


def data_dir() -> Path:
    default = APP_DIR.parent / 'exercises' / 'dane'
    if not default.exists():
        default = APP_DIR / 'dane'
    return Path(os.getenv('DATA_DIR', str(default))).expanduser().resolve()


def log_dir() -> Path:
    return Path(os.getenv('LOG_DIR', str(APP_DIR / 'logs'))).expanduser().resolve()


def cache_dir() -> Path:
    return Path(os.getenv('CACHE_DIR', str(APP_DIR / 'cache'))).expanduser().resolve()
