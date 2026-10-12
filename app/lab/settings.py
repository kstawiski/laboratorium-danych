"""Tryb pracy i atomowy zapis ustawień użytkownika, bez cache i logowania kluczy."""
import json
import os
from pathlib import Path
import tempfile


def public_mode():
    return os.getenv('LAB_PUBLIC_SERVER') == '1'


def user_dir():
    return Path(os.getenv('LAB_USER_DIR', str(Path.home() / '.laboratorium-danych'))).expanduser().resolve()


def settings_path():
    return user_dir() / 'ustawienia.json'


def load_settings():
    if public_mode():
        return {}
    try:
        value = json.loads(settings_path().read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError
        text_fields = ('ai_provider', 'google_key', 'endpoint_url', 'endpoint_key', 'endpoint_model', 'chosen_model')
        for name in text_fields:
            if name in value and not isinstance(value[name], str) and not (name == 'chosen_model' and value[name] is None):
                raise ValueError
        for name in ('google_verified', 'endpoint_verified'):
            if name in value and (not isinstance(value[name], list) or any(not isinstance(item, str) for item in value[name])):
                raise ValueError
        return value
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        raise ValueError('Nie można odczytać ustawień. Otwórz panel Model AI i ustaw model ponownie.') from None


def save_settings(value):
    if public_mode():
        return
    temporary = None
    try:
        directory = user_dir()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                                         prefix='.ustawienia-', delete=False) as handle:
            temporary = handle.name
            if os.name != 'nt':
                os.fchmod(handle.fileno(), 0o600)
            json.dump(value, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, settings_path())
    except (OSError, ValueError, TypeError):
        raise ValueError('Nie można zapisać ustawień. Sprawdź, czy masz miejsce na dysku i prawo zapisu w swoim katalogu użytkownika.') from None
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
