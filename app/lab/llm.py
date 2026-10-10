"""Klient OpenAI: JSON, globalne limity w procesie, cache i log bez treści."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import os
import tempfile
import threading
import time
from typing import Callable
from openai import OpenAI, APIError, APIConnectionError, APITimeoutError, RateLimitError, BadRequestError
from .config import ModelConfig, log_dir, cache_dir

class ModelError(RuntimeError):
    pass

class OptionalAuthOpenAI(OpenAI):
    def __init__(self, *, api_key="", **kwargs):
        super().__init__(api_key=api_key, _enforce_credentials=bool(api_key), **kwargs)

    @property
    def auth_headers(self):
        return super().auth_headers if self.api_key else {}

    def _validate_headers(self, headers, custom_headers):
        if self.api_key:
            super()._validate_headers(headers, custom_headers)

@dataclass(frozen=True)
class ModelResult:
    value: dict | list
    tokens: int
    elapsed: float
    cached: bool = False
    json_mode: str = ""

_LOCK = threading.RLock()
_CONDITION = threading.Condition(_LOCK)
_LOG_LOCK = threading.Lock()
_SEMAPHORES = {}  # Jeden limit globalny dla modelu, również przy kilku serwerach.
_SERVER_SEMAPHORES = {}
_ACTIVE = {}
_INFLIGHT = set()
BUSY_MESSAGE = "Serwer modelu jest zajęty, spróbuj za chwilę lub wybierz model zapasowy Qwen w panelu."


def _remove_trailing_commas(text):
    result, in_string, escaped = [], False, False
    for index, char in enumerate(text):
        if char == '"' and not escaped:
            in_string = not in_string
        if char == ',' and not in_string and text[index+1:].lstrip().startswith(('}', ']')):
            continue
        result.append(char)
        escaped = (char == '\\' and not escaped) if in_string else False
    return ''.join(result)


def parse_json(text: str):
    if not isinstance(text, str) or len(text) > 1_000_000:
        raise ModelError("Odpowiedź modelu jest pusta albo zbyt długa.")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip().lstrip("\ufeff")
    def reject(value):
        raise ValueError("Niefinitywna liczba w JSON")
    decoder = json.JSONDecoder(parse_constant=reject)
    for candidate in (_remove_trailing_commas(text), text):
        for match in re.finditer(r"[\[{]", candidate):
            try:
                value, _ = decoder.raw_decode(candidate[match.start():])
                if isinstance(value, (dict, list)):
                    return value
            except (ValueError, json.JSONDecodeError):
                continue
    raise ModelError("Model nie zwrócił poprawnego JSON. Zmień prompt lub wybierz drugi model.")


def validate_json(value, schema: dict, path: str = "wynik"):
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                validate_json(value, option, path)
                return
            except ModelError:
                pass
        raise ModelError(f"Pole {path} ma typ niezgodny ze schematem.")
    types = schema.get("type", [])
    types = [types] if isinstance(types, str) else types
    checks = {"null": lambda x: x is None, "object": lambda x: isinstance(x, dict),
              "array": lambda x: isinstance(x, list), "string": lambda x: isinstance(x, str),
              "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
              "integer": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and float(x).is_integer(), "boolean": lambda x: isinstance(x, bool)}
    if types and not any(checks.get(t, lambda x: False)(value) for t in types):
        raise ModelError(f"Pole {path} ma typ niezgodny ze schematem.")
    if "enum" in schema and value not in schema["enum"]:
        raise ModelError(f"Pole {path} ma wartość spoza dozwolonych kategorii.")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        if missing:
            raise ModelError(f"Brak pól JSON: {', '.join(sorted(missing))}.")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ModelError("Model zwrócił pola spoza schematu.")
        for name, child in properties.items():
            if name in value:
                validate_json(value[name], child, f"{path}.{name}")
    elif isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ModelError(f"Pole {path} zawiera zbyt wiele pozycji.")
        for index, item in enumerate(value):
            validate_json(item, schema.get("items", {}), f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"] or "maximum" in schema and value > schema["maximum"]:
            raise ModelError(f"Pole {path} jest poza zakresem schematu.")
    elif isinstance(value, str):
        if schema.get("pattern") and re.search(schema["pattern"], value) is None:
            raise ModelError(f"Pole {path} ma zapis niezgodny ze schematem.")
        if schema.get("format") == "date":
            from datetime import date
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ModelError(f"Pole {path} nie jest poprawną datą.") from exc


def structural_schema(schema):
    """W ekstrakcji pozwala pokazać błędną wartość jako rozbieżność z kluczem."""
    if isinstance(schema, list):
        return [structural_schema(value) for value in schema]
    if isinstance(schema, dict):
        return {key: structural_schema(value) for key, value in schema.items()
                if key not in {"enum", "minimum", "maximum", "pattern", "format"}}
    return schema


def prepared_messages(messages, schema):
    return [{"role": "system", "content": "Zwróć wyłącznie JSON zgodny ze schematem: " +
             json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}] + messages


def _cache_key(config, messages, temperature, max_tokens):
    content = json.dumps([config.model, messages, temperature, max_tokens],
                         sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(content.encode()).hexdigest()


def _read_cache(key, validation_schema, start):
    file = cache_dir() / (key + ".json")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        validate_json(data["value"], validation_schema)
        return ModelResult(data["value"], int(data["tokens"]), time.monotonic() - start,
                           cached=True, json_mode=data["json_mode"])
    except FileNotFoundError:
        return None
    except (ValueError, KeyError, TypeError, ModelError):
        # Niepełny lub niezgodny wpis nie blokuje nowego zapytania.
        return None
    except OSError as exc:
        raise ModelError("Nie można odczytać pamięci podręcznej. Sprawdź uprawnienia CACHE_DIR.") from exc


def _write_cache(key, result):
    directory = cache_dir()
    temporary = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".cache-", suffix=".tmp", delete=False) as handle:
            temporary = handle.name
            json.dump({"value": result.value, "tokens": result.tokens, "json_mode": result.json_mode},
                      handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, directory / (key + ".json"))
    except OSError as exc:
        raise ModelError("Nie można zapisać pamięci podręcznej. Sprawdź uprawnienia CACHE_DIR.") from exc
    finally:
        if temporary and os.path.exists(temporary): os.unlink(temporary)


def _reserve_server(config, deadline, excluded, on_queue):
    reported = False
    with _CONDITION:
        while True:
            candidates = [u for u in config.servers if u not in excluded]
            candidates.sort(key=lambda u: _ACTIVE.get((u, config.model), 0))
            for url in candidates:
                key = (url, config.model)
                sem = _SERVER_SEMAPHORES.setdefault(key, threading.BoundedSemaphore(config.per_server_concurrency))
                if sem.acquire(blocking=False):
                    _ACTIVE[key] = _ACTIVE.get(key, 0) + 1
                    return url, sem
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise ModelError(BUSY_MESSAGE)
            if on_queue and not reported:
                on_queue()
                reported = True
            _CONDITION.wait(remaining)


def _release_server(config, url, semaphore):
    with _CONDITION:
        _ACTIVE[(url, config.model)] -= 1
        semaphore.release()
        _CONDITION.notify_all()


def _log(config, group, tab, result=None, status="ok", elapsed=0):
    now = datetime.now(timezone.utc)
    clean = lambda text: re.sub(r"[\r\n\x00-\x1f]", " ", str(text))[:80]
    record = {"czas": now.isoformat(), "grupa": clean(group), "zakladka": clean(tab), "model": config.model,
              "liczba_tokenow": result.tokens if result and not result.cached else 0,
              "czas_odpowiedzi_s": round(result.elapsed if result else elapsed, 3),
              "cache": bool(result and result.cached), "status": status, "json_mode": result.json_mode if result else ""}
    directory = log_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with _LOG_LOCK, (directory / f"zapytania-{now:%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise ModelError("Nie można zapisać logu zapytań. Sprawdź uprawnienia katalogu logs.") from exc


def _unsupported(exc) -> bool:
    if not isinstance(exc, BadRequestError) and getattr(exc, "status_code", None) not in {400, 422}:
        return False
    text = str(getattr(exc, "body", "") or exc).lower()
    return any(word in text for word in ("response_format", "response format", "json_schema", "json schema", "json_object", "json object", "structured output"))


def call_model(config: ModelConfig, messages: list[dict], schema: dict, temperature=.2,
               bypass_cache=False, group="", tab="", on_queue: Callable | None = None,
               client_factory=None, score_extraction=False, max_tokens=700) -> ModelResult:
    """Trwały cache; 6 zapytań/model, osobny limit/serwer, jeden retry połączenia."""
    start = time.monotonic()
    deadline = start + config.timeout
    prepared = prepared_messages(messages, schema)
    key = _cache_key(config, prepared, temperature, max_tokens)
    validation_schema = structural_schema(schema) if score_extraction else schema
    owns_flight, acquired = False, False
    semaphore = None
    try:
        if not bypass_cache:
            with _CONDITION:
                while True:
                    result = _read_cache(key, validation_schema, start)
                    if result:
                        _log(config, group, tab, result)
                        return result
                    if key not in _INFLIGHT:
                        _INFLIGHT.add(key)
                        owns_flight = True
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0: raise ModelError(BUSY_MESSAGE)
                    if on_queue: on_queue()
                    _CONDITION.wait(remaining)
        with _LOCK:
            semaphore = _SEMAPHORES.setdefault(config.model, threading.BoundedSemaphore(min(6, config.concurrency)))
        acquired = semaphore.acquire(blocking=False)
        if not acquired:
            if on_queue: on_queue()
            acquired = semaphore.acquire(timeout=max(0, deadline - time.monotonic()))
        if not acquired: raise ModelError(BUSY_MESSAGE)
        excluded, response, mode = set(), None, ''
        for attempt in range(min(2, len(config.servers))):
            url, server_sem = _reserve_server(config, deadline, excluded, on_queue)
            client = None
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise ModelError(BUSY_MESSAGE)
                client = (client_factory or OptionalAuthOpenAI)(base_url=url, api_key=config.api_key,
                                                              timeout=remaining, max_retries=0)
                formats = [("json_schema", {"type": "json_schema", "json_schema": {"name": "wynik", "strict": True, "schema": schema}}),
                           ("json_object", {"type": "json_object"}), ("prompt_json", None)]
                for mode, response_format in formats:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0: raise ModelError(BUSY_MESSAGE)
                    arguments = dict(model=config.model, messages=prepared, temperature=temperature,
                                     max_tokens=max_tokens, timeout=remaining)
                    if response_format: arguments["response_format"] = response_format
                    # Nie wysyłamy parametrów włączających rozumowanie.
                    try:
                        response = client.chat.completions.create(**arguments)
                        break
                    except APIError as exc:
                        if response_format and _unsupported(exc): continue
                        raise
                break
            except APIConnectionError:
                excluded.add(url)
                if attempt + 1 >= min(2, len(config.servers)): raise
            finally:
                try:
                    if client is not None and hasattr(client, 'close'): client.close()
                finally:
                    _release_server(config, url, server_sem)
        if response is None or not response.choices:
            raise ModelError("Model zwrócił pustą odpowiedź.")
        if response.choices[0].finish_reason == 'length':
            raise ModelError("Model przerwał odpowiedź przed końcem. Wybierz mniej danych lub skróć polecenie.")
        value = parse_json(response.choices[0].message.content or '')
        validate_json(value, validation_schema)
        tokens = getattr(response.usage, 'total_tokens', 0) or 0
        result = ModelResult(value, tokens, time.monotonic() - start, json_mode=mode)
        if not bypass_cache: _write_cache(key, result)
        _log(config, group, tab, result)
        return result
    except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
        _log(config, group, tab, status='serwer_niedostepny', elapsed=time.monotonic() - start)
        raise ModelError(BUSY_MESSAGE) from exc
    except APIError as exc:
        _log(config, group, tab, status='blad_api', elapsed=time.monotonic() - start)
        raise ModelError("Nie udało się wywołać modelu. Sprawdź adres i klucz lub wybierz model zapasowy Qwen.") from exc
    except ModelError:
        _log(config, group, tab, status='blad', elapsed=time.monotonic() - start)
        raise
    finally:
        if acquired: semaphore.release()
        if owns_flight:
            with _CONDITION:
                _INFLIGHT.discard(key)
                _CONDITION.notify_all()
