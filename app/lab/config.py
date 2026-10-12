from dataclasses import dataclass, field
from pathlib import Path
import os

APP_DIR = Path(__file__).resolve().parent.parent

@dataclass(frozen=True)
class ModelConfig:
    label: str
    model: str
    base_url: str
    api_key: str = field(repr=False)
    timeout: float = 180.0
    concurrency: int = 6
    base_urls: tuple[str, ...] = ()
    per_server_concurrency: int = 4
    reasoning_effort: str = ''
    transport: str = 'openai'
    download_size: int = 0
    session_only: bool = False

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
    configs = {}
    for prefix, label_default, model_default, per_server in (
        ('ORNITH', 'Ornith', 'ornith-1.5-9b', 4), ('QWEN', 'Qwen', 'umed-qwen', 6)
    ):
        base = os.getenv(prefix + '_BASE_URL', '').strip().rstrip('/')
        urls = tuple(dict.fromkeys(u.strip().rstrip('/') for u in os.getenv(prefix + '_BASE_URLS', '').split(',') if u.strip()))
        if not base and not urls:
            continue
        limit = int(os.getenv(prefix + '_MAX_CONCURRENCY_PER_SERVER', str(per_server)))
        if limit < 1:
            raise ValueError('Limit na serwer musi być dodatni.')
        label = os.getenv(prefix + '_LABEL', label_default)
        configs[label] = ModelConfig(label, os.getenv(prefix + '_MODEL', model_default),
                                     urls[0] if urls else base, secret(prefix + '_API_KEY'),
                                     base_urls=urls, per_server_concurrency=limit,
                                     reasoning_effort=os.getenv(prefix + '_REASONING_EFFORT', ''))
    return configs


def data_dir() -> Path:
    default = APP_DIR.parent / 'exercises' / 'dane'
    if not default.exists():
        default = APP_DIR / 'dane'
    return Path(os.getenv('DATA_DIR', str(default))).expanduser().resolve()


def log_dir() -> Path:
    return Path(os.getenv('LOG_DIR', str(_runtime_dir() / 'logs'))).expanduser().resolve()


def cache_dir() -> Path:
    return Path(os.getenv('CACHE_DIR', str(_runtime_dir() / 'cache'))).expanduser().resolve()


def _runtime_dir():
    from .settings import public_mode, user_dir
    return APP_DIR if public_mode() else user_dir()
