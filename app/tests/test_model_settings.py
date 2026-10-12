"""Tryby, zapis ustawień, UI i natywna Ollama. Wyłącznie mocki sieci."""
from pathlib import Path
from types import SimpleNamespace
import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import httpx
import pytest
from streamlit.testing.v1 import AppTest
import lab.model_ui as ui
import lab.settings as settings
import lab.endpoints as endpoints
import lab.llm as llm
from lab.config import ModelConfig, model_configs, cache_dir, log_dir
from lab.local_models import context_size, recommended_model, RECOMMENDED_MODELS
from lab.prompts import TEXT_SCHEMA
from tests.test_llm import FakeClient, response

APP = Path(__file__).resolve().parent.parent / 'app.py'


def no_operator(monkeypatch):
    for prefix in ('ORNITH', 'QWEN'):
        for suffix in ('BASE_URL', 'BASE_URLS', 'MODEL', 'LABEL', 'REASONING_EFFORT'):
            monkeypatch.delenv(prefix + '_' + suffix, raising=False)


def start():
    app = AppTest.from_file(str(APP), default_timeout=180).run()
    assert not app.exception
    return app


@pytest.mark.parametrize('value,expected', [(None, False), ('0', False), ('1', True), ('true', False)])
def test_mode(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('LAB_PUBLIC_SERVER', raising=False)
    else:
        monkeypatch.setenv('LAB_PUBLIC_SERVER', value)
    monkeypatch.setenv('LAB_DESKTOP', '1')
    assert settings.public_mode() is expected


def test_hidden_unset_operator_models(monkeypatch):
    no_operator(monkeypatch)
    assert model_configs() == {}
    monkeypatch.setenv('ORNITH_LABEL', 'Własna etykieta')
    monkeypatch.setenv('ORNITH_API_KEY', 'fixture-key')
    monkeypatch.setenv('ORNITH_MODEL', 'named-only')
    assert model_configs() == {}
    monkeypatch.setenv('QWEN_BASE_URL', 'http://operator/v1')
    assert list(model_configs()) == ['Qwen']


def test_local_settings_atomic_permissions_and_restart(monkeypatch, tmp_path):
    data = {'google_key': 'fixture-google-key', 'chosen_model': 'Google: gemma-4-31b-it'}
    settings.save_settings(data)
    path = settings.settings_path()
    assert path.name == 'ustawienia.json' and path.parent == tmp_path / 'user'
    assert settings.load_settings() == data
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600
    old = path.read_bytes()
    def failed(*args):
        raise OSError('private path and fixture-google-key')
    monkeypatch.setattr(settings.os, 'replace', failed)
    with pytest.raises(ValueError) as exc:
        settings.save_settings({'google_key': 'new-key'})
    assert 'fixture-google-key' not in str(exc.value)
    assert path.read_bytes() == old
    assert list(path.parent.iterdir()) == [path]


def test_settings_fallback_and_runtime_dirs(monkeypatch, tmp_path):
    monkeypatch.delenv('LAB_USER_DIR')
    monkeypatch.delenv('CACHE_DIR')
    monkeypatch.delenv('LOG_DIR')
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    assert settings.settings_path() == tmp_path / '.laboratorium-danych' / 'ustawienia.json'
    assert cache_dir() == tmp_path / '.laboratorium-danych' / 'cache'
    assert log_dir() == tmp_path / '.laboratorium-danych' / 'logs'


def test_public_settings_do_not_read_or_write(monkeypatch):
    settings.save_settings({'google_key': 'local-private-key'})
    before = settings.settings_path().read_bytes()
    monkeypatch.setenv('LAB_PUBLIC_SERVER', '1')
    assert settings.load_settings() == {}
    settings.save_settings({'google_key': 'public-key'})
    assert settings.settings_path().read_bytes() == before


def test_settings_errors_do_not_show_contents():
    settings.settings_path().parent.mkdir(parents=True)
    settings.settings_path().write_text('private-key-invalid-json')
    with pytest.raises(ValueError) as exc:
        settings.load_settings()
    assert 'private-key' not in str(exc.value)


def mock_http(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(llm.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    endpoints._CACHE.clear()


def test_native_ollama_body_result_and_cache(monkeypatch):
    requests, client_options = [], []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'done': True, 'done_reason': 'stop',
                               'message': {'content': '{"odpowiedz":"OK"}'},
                               'prompt_eval_count': 50, 'eval_count': 7})
    original = httpx.Client
    def client(**kwargs):
        client_options.append(kwargs)
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(llm.httpx, 'Client', client)
    config = ModelConfig('Ollama', 'native-test', 'http://ollama:11434', '', timeout=600,
                         concurrency=1, per_server_concurrency=1, transport='ollama')
    messages = [{'role': 'user', 'content': 'x' * 24000}]
    result = llm.call_model(config, messages, TEXT_SCHEMA, max_tokens=700)
    assert result.tokens == 57 and result.json_mode == 'ollama_schema' and not result.cached
    assert result.value == {'odpowiedz': 'OK'}
    body = json.loads(requests[0].content)
    assert requests[0].url.path == '/api/chat'
    assert body['stream'] is False and body['think'] is False and body['keep_alive'] == '15m'
    assert body['format'] == TEXT_SCHEMA
    assert body['options'] == {'num_ctx': 12288, 'temperature': .2, 'num_predict': 700}
    assert body['messages'] == llm.prepared_messages(messages, TEXT_SCHEMA)
    assert requests[0].extensions['timeout']['read'] > 590
    assert client_options[0]['trust_env'] is False
    assert llm.call_model(config, messages, TEXT_SCHEMA, max_tokens=700).cached
    assert len(requests) == 1


@pytest.mark.parametrize('data,message', [
    ({'done': True, 'done_reason': 'length', 'message': {'content': '{"odpowiedz":"OK"}'}}, 'przerwał'),
    ({'done': True, 'message': {'content': 'invalid JSON'}}, 'poprawnego JSON'),
    ({'error': 'private-key'}, 'Ollama nie odpowiedziała'),
])
def test_native_ollama_errors(monkeypatch, data, message):
    mock_http(monkeypatch, lambda _: httpx.Response(200, json=data))
    config = ModelConfig('o', 'native-errors', 'http://ollama', '', transport='ollama')
    with pytest.raises(llm.ModelError) as exc:
        llm.call_model(config, [], TEXT_SCHEMA, bypass_cache=True)
    assert message in str(exc.value) and 'private-key' not in str(exc.value)


def test_context_bounds_and_recommendations():
    assert context_size([], 32) == 8192
    assert context_size([{'content': 'x' * 1000000}], 2500) == 32768
    assert context_size([{'content': 'x' * 24000}], 2500) == 12288
    assert recommended_model(16).name == 'gemma4:12b'
    assert recommended_model(15.9).name == 'gemma4:e4b'
    assert recommended_model(12).name == 'gemma4:e4b'
    assert recommended_model(None).name == 'gemma4:12b'
    assert not RECOMMENDED_MODELS[2].default


def test_pull_progress_mock_stream(monkeypatch):
    requests, progress = [], []
    payload = '\n'.join(json.dumps(item) for item in [
        {'status': 'pulling manifest'}, {'digest': 'a', 'total': 100, 'completed': 25},
        {'digest': 'a', 'total': 100, 'completed': 100},
        {'digest': 'b', 'total': 20, 'completed': 10},
        {'digest': 'b', 'total': 20, 'completed': 20}, {'status': 'success'}]) + '\n'
    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=payload.encode())
    mock_http(monkeypatch, handler)
    endpoints._CACHE['http://ollama'] = (0, {}, None)
    endpoints.pull_model('http://ollama', 'gemma4:12b', lambda *args: progress.append(args))
    assert requests[0].url.path == '/api/pull'
    assert json.loads(requests[0].content) == {'model': 'gemma4:12b', 'stream': True}
    assert progress[1] == (.25, 25, 100)
    assert progress[3] == (110/120, 110, 120)
    assert progress[-1] == (1.0, 120, 120)
    assert 'http://ollama' not in endpoints._CACHE


@pytest.mark.parametrize('payload', ['{"error":"private-key"}\n', '{"status":"pulling manifest"}\n', 'invalid'])
def test_pull_errors_are_plain_and_private(monkeypatch, payload):
    mock_http(monkeypatch, lambda _: httpx.Response(200, content=payload.encode()))
    with pytest.raises(ValueError) as exc:
        endpoints.pull_model('http://ollama', 'gemma4:12b', lambda *args: None)
    assert 'Nie udało się pobrać' in str(exc.value) and 'private-key' not in str(exc.value)


def test_api_keys_absent_from_logs_cache_and_errors(monkeypatch):
    secret = 'fixture-key-never-log-or-cache'
    config = ModelConfig('keyed', 'keyed-model', 'http://test/v1', secret)
    factory = lambda **kwargs: FakeClient(lambda _: response('{"odpowiedz":"OK"}'), **kwargs)
    llm.call_model(config, [], TEXT_SCHEMA, client_factory=factory)
    assert secret not in repr(config)
    for folder in (cache_dir(), log_dir()):
        for path in folder.glob('*'):
            assert secret not in path.name and secret not in path.read_text()
    other = ModelConfig('keyed', 'keyed-model', 'http://test/v1', 'second-key')
    assert llm._cache_key(config, [], .2, 700) == llm._cache_key(other, [], .2, 700)
    cloud = ModelConfig('g', 'private-cloud-model', ui.GOOGLE_URL, secret, session_only=True)
    before = set(cache_dir().glob('*'))
    llm.call_model(cloud, [], TEXT_SCHEMA, client_factory=factory)
    assert set(cache_dir().glob('*')) == before


def test_first_run_guide_and_local_providers_without_variables(monkeypatch):
    no_operator(monkeypatch)
    at = start()
    assert len(at.get('tab')) == 7
    assert at.selectbox(key='chosen_model').options == []
    assert any(item.value == 'Uruchom swój pierwszy model AI' for item in at.subheader)
    assert at.radio(key='ai_provider').options == [ui.OLLAMA, ui.GOOGLE, ui.CUSTOM]
    assert at.button(key='start_pull:gemma4:12b').disabled
    assert any('ollama.com/download' in item.value for item in at.markdown)
    at.selectbox(key='eda_variable').select('rt_dose_gy').run()
    at.button(key='eda_ai').click().run()
    assert not at.exception and any('Najpierw skonfiguruj model' in item.value for item in at.info)


def test_public_mode_hides_local_and_custom_even_with_legacy_flags(monkeypatch):
    no_operator(monkeypatch)
    settings.save_settings({'endpoint_url': 'http://private', 'endpoint_key': 'local-secret',
                            'endpoint_verified': ['local'], 'google_key': 'local-google'})
    monkeypatch.setenv('LAB_PUBLIC_SERVER', '1')
    monkeypatch.setenv('ALLOW_CUSTOM_ENDPOINT', '1')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://private')
    def forbidden(*args):
        raise AssertionError('Publiczny serwer nie może wywoływać lokalnych adresów')
    monkeypatch.setattr(ui, '_discover_ollama', forbidden)
    monkeypatch.setattr(endpoints, 'endpoint_models', forbidden)
    at = start()
    assert at.radio(key='ai_provider').options == [ui.GOOGLE]
    assert not at.text_input(key='google_key').value
    assert not any(x.key == 'endpoint_url' for x in at.text_input)
    assert not any(x.key.startswith('start_pull:') for x in at.button)
    assert at.selectbox(key='chosen_model').options == []
    monkeypatch.setenv('ORNITH_BASE_URL', 'http://operator/v1')
    at = start()
    assert at.selectbox(key='chosen_model').options == ['Ornith']


def test_recommended_installed_model_and_remembered_choice(monkeypatch):
    no_operator(monkeypatch)
    monkeypatch.setattr(ui, 'total_ram_gb', lambda: 32)
    models = {f'Ollama: {name}': ModelConfig(f'Ollama: {name}', name, 'http://ollama', '', transport='ollama')
              for name in ('ornith-1.5:9b', 'gemma4:12b')}
    monkeypatch.setattr(ui, '_discover_ollama', lambda _: (models, None))
    at = start()
    assert at.selectbox(key='chosen_model').value == 'Ollama: gemma4:12b'
    at.selectbox(key='chosen_model').select('Ollama: ornith-1.5:9b').run()
    assert settings.load_settings()['chosen_model'] == 'Ollama: ornith-1.5:9b'
    assert start().selectbox(key='chosen_model').value == 'Ollama: ornith-1.5:9b'


def test_google_check_fixed_url_minimal_and_persistence(monkeypatch):
    no_operator(monkeypatch)
    calls = []
    def mocked(config, *args, **kwargs):
        calls.append((config, kwargs))
        return SimpleNamespace(value={'ok': True})
    monkeypatch.setattr(ui, 'call_model', mocked)
    at = start()
    at.radio(key='ai_provider').set_value(ui.GOOGLE).run()
    at.text_input(key='google_key').set_value('fixture-google-key').run()
    at.button(key='google_check').click().run()
    assert not at.exception
    config, kwargs = calls[0]
    assert config.base_url == ui.GOOGLE_URL and config.reasoning_effort == 'minimal'
    assert config.api_key == 'fixture-google-key' and kwargs['bypass_cache'] and kwargs['max_tokens'] == 32
    assert at.selectbox(key='chosen_model').value == 'Google: gemma-4-31b-it'
    assert settings.load_settings()['google_key'] == 'fixture-google-key'
    assert start().selectbox(key='chosen_model').value == 'Google: gemma-4-31b-it'
    at.radio(key='ai_provider').set_value(ui.OLLAMA).run()
    at.text_input(key='group').set_value('Test ponownego renderowania').run()
    assert 'Google: gemma-4-31b-it' in at.selectbox(key='chosen_model').options
    assert settings.load_settings()['google_key'] == 'fixture-google-key'
    at.radio(key='ai_provider').set_value(ui.GOOGLE).run()
    at.text_input(key='google_key').set_value('changed-key').run()
    assert at.selectbox(key='chosen_model').options == []


def test_desktop_missing_package_has_actionable_message(monkeypatch, tmp_path):
    monkeypatch.setenv('LAB_DESKTOP', '1')
    monkeypatch.setenv('DATA_DIR', str(tmp_path / 'absent'))
    at = start()
    assert any('zainstaluj ponownie Laboratorium danych' in item.value for item in at.error)
    assert not any('fixture' in item.value for item in at.warning)
    assert not at.get('tab')


def test_ollama_serializes_different_models_on_same_computer(monkeypatch):
    entered, second, release = Event(), Event(), Event()
    def handler(request):
        name = json.loads(request.content)['model']
        if name == 'serial-first':
            entered.set()
            assert release.wait(10)
        else:
            second.set()
        return httpx.Response(200, json={'done': True, 'message': {'content': '{"odpowiedz":"OK"}'}})
    mock_http(monkeypatch, handler)
    def call(name):
        config = ModelConfig('o', name, 'http://serial-ollama', '', timeout=600,
                             concurrency=1, per_server_concurrency=1, transport='ollama')
        return llm.call_model(config, [], TEXT_SCHEMA, bypass_cache=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(call, 'serial-first')
        assert entered.wait(10)
        other = pool.submit(call, 'serial-second')
        try:
            assert not second.wait(.2)
        finally:
            release.set()
        assert first.result().value == other.result().value == {'odpowiedz': 'OK'}
    assert second.is_set()


def test_api_failure_does_not_expose_key_in_message_trace_or_log():
    import traceback
    from openai import APIError
    secret = 'fixture-private-api-failure'
    config = ModelConfig('keyed', 'api-failure-test', 'http://test/v1', secret)
    def failed(_):
        raise APIError(secret, httpx.Request('POST', 'http://test/v1'), body={'message': secret})
    factory = lambda **kwargs: FakeClient(failed, **kwargs)
    with pytest.raises(llm.ModelError) as exc:
        llm.call_model(config, [], TEXT_SCHEMA, client_factory=factory, bypass_cache=True)
    assert secret not in ''.join(traceback.format_exception(exc.value))
    assert all(secret not in path.read_text() for path in log_dir().glob('*'))


def test_detection_sizes_native_config_and_refresh(monkeypatch):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={'models': [{'name': 'gemma4:12b', 'size': 8000000000}]})
    mock_http(monkeypatch, handler)
    configs, note = endpoints.ollama_models('http://127.0.0.1:11434')
    config = configs['Ollama: gemma4:12b']
    assert note is None and config.download_size == 8000000000
    assert config.timeout == 600 and config.concurrency == config.per_server_concurrency == 1
    assert config.transport == 'ollama' and config.base_url == 'http://127.0.0.1:11434'
    assert seen[0].url.path == '/api/tags'
    endpoints.refresh_ollama(config.base_url)
    endpoints.ollama_models(config.base_url)
    assert len(seen) == 2


def test_protocol_error_and_metadata_do_not_expose_key():
    import traceback
    secret = 'fixture-private-protocol-key'
    config = ModelConfig('keyed', 'protocol-' + secret, 'http://test/v1', secret)
    def failed(_):
        raise ValueError('Invalid header: ' + secret)
    factory = lambda **kwargs: FakeClient(failed, **kwargs)
    with pytest.raises(llm.ModelError) as exc:
        llm.call_model(config, [], TEXT_SCHEMA, client_factory=factory, bypass_cache=True,
                       group=secret, tab=secret)
    assert secret not in ''.join(traceback.format_exception(exc.value))
    assert all(secret not in path.read_text() for path in log_dir().glob('*'))


def test_validation_error_redacts_key_from_message_and_trace():
    import traceback
    secret = 'fixture-private-validation-key'
    config = ModelConfig('keyed', 'validation-key', 'http://test/v1', secret)
    schema = {'type': 'object', 'properties': {secret: {'type': 'string'}}, 'required': [secret]}
    factory = lambda **kwargs: FakeClient(lambda _: response('{}'), **kwargs)
    with pytest.raises(llm.ModelError) as exc:
        llm.call_model(config, [], schema, client_factory=factory, bypass_cache=True)
    assert secret not in str(exc.value)
    assert secret not in ''.join(traceback.format_exception(exc.value))
