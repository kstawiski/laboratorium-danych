from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from threading import Event, Lock
import json
import time
import httpx
import pytest
from openai import BadRequestError, RateLimitError
from lab.config import ModelConfig, model_configs
from lab.llm import call_model, ModelError, OptionalAuthOpenAI, _SEMAPHORES, _SERVER_SEMAPHORES, _ACTIVE, _INFLIGHT
from lab.prompts import TEXT_SCHEMA, clinical_messages

@pytest.fixture(autouse=True)
def clear_cache():
    _SERVER_SEMAPHORES.clear()
    _ACTIVE.clear()
    _INFLIGHT.clear()
    _SEMAPHORES.clear()

class FakeClient:
    def __init__(self, action, **kwargs):
        self.action = action
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
    def create(self, **kwargs):
        return self.action(kwargs)
    def close(self): pass


def response(text='{"odpowiedz":"OK"}'):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason='stop')], usage=SimpleNamespace(total_tokens=12))


def test_cache_bypass_metadata_only(tmp_path):
    calls = []
    def action(arguments):
        calls.append(arguments)
        return response()
    cfg = ModelConfig('Test','test','http://test/v1','')
    factory = lambda **kw: FakeClient(action, **kw)
    messages = [{'role':'user','content':'TREŚĆ_DOKUMENTU_NIE_LOGUJ'}]
    first = call_model(cfg,messages,TEXT_SCHEMA,group='Grupa 1',tab='Ekstrakcja',client_factory=factory)
    cached = call_model(cfg,messages,TEXT_SCHEMA,group='Grupa 2',tab='Ekstrakcja',client_factory=factory)
    forced = call_model(cfg,messages,TEXT_SCHEMA,bypass_cache=True,client_factory=factory)
    assert len(calls) == 2 and not first.cached and cached.cached and not forced.cached
    assert calls[0]['response_format']['type'] == 'json_schema'
    logs = list((tmp_path/'logs').glob('*.jsonl'))
    raw = logs[0].read_text()
    assert 'TREŚĆ_DOKUMENTU' not in raw and 'content' not in raw
    items = [json.loads(line) for line in raw.splitlines()]
    assert [item['liczba_tokenow'] for item in items] == [12,0,12]
    assert items[0]['grupa'] == 'Grupa 1'


def test_json_schema_fallback():
    formats = []
    def action(arguments):
        mode = arguments.get('response_format',{}).get('type','prompt')
        formats.append(mode)
        if mode != 'prompt':
            raise BadRequestError('unsupported response_format',response=httpx.Response(400,request=httpx.Request('POST','http://test/v1')),body={'error':'response_format unsupported'})
        return response('```json\n{"odpowiedz":"OK",}\n```')
    result = call_model(ModelConfig('t','t','http://test/v1',''),[],TEXT_SCHEMA,client_factory=lambda **kw: FakeClient(action,**kw))
    assert formats == ['json_schema','json_object','prompt']
    assert result.json_mode == 'prompt_json'


def test_busy_server_error_polish():
    def action(arguments):
        raise RateLimitError('busy',response=httpx.Response(429,request=httpx.Request('POST','http://test/v1')),body={})
    with pytest.raises(ModelError, match='Serwer modelu jest zajęty'):
        call_model(ModelConfig('t','t','http://test/v1','',timeout=.01),[],TEXT_SCHEMA,client_factory=lambda **kw: FakeClient(action,**kw))


def test_semaphore_is_shared_and_queue_reported():
    active, maximum = 0, 0
    lock, release, two_started, queued = Lock(), Event(), Event(), Event()
    def action(arguments):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum,active)
            if active == 2: two_started.set()
        assert release.wait(5)
        with lock: active -= 1
        return response()
    cfg = ModelConfig('t','parallel','http://test/v1','',timeout=5,concurrency=2)
    def job(index):
        return call_model(cfg,[{'role':'user','content':str(index)}],TEXT_SCHEMA,on_queue=queued.set,client_factory=lambda **kw: FakeClient(action,**kw))
    with ThreadPoolExecutor(max_workers=3) as pool:
        first, second = pool.submit(job,1), pool.submit(job,2)
        assert two_started.wait(3)
        third = pool.submit(job,3)
        assert queued.wait(3)
        release.set()
        assert all(f.result().value['odpowiedz'] == 'OK' for f in (first,second,third))
    assert maximum == 2


def test_notes_excluded_and_ten_row_batch(dirty, definitions):
    messages = clinical_messages(dirty.iloc[:10],definitions)
    data = json.loads(messages[1]['content'])
    assert len(data['wiersze']) == 10
    assert all('notes' not in row for row in data['wiersze'])
    with_notes = json.loads(clinical_messages(dirty.iloc[:10],definitions,True)[1]['content'])
    assert all('notes' in row for row in with_notes['wiersze'])


def test_local_server_requires_no_dummy_key():
    from lab.llm import OptionalAuthOpenAI
    client = OptionalAuthOpenAI(base_url='http://localhost:1234/v1',api_key='')
    assert client.auth_headers == {}
    client.close()


def test_key_file_configuration(monkeypatch, tmp_path):
    path = tmp_path/'secret'
    # Wyłącznie sztuczna wartość testowa, nie klucz API.
    path.write_text('fixture-secret-value\n')
    monkeypatch.setenv('ORNITH_API_KEY_FILE',str(path))
    monkeypatch.setenv('ORNITH_MODEL','local-model')
    cfg = model_configs()['Ornith']
    assert cfg.api_key == 'fixture-secret-value' and cfg.model == 'local-model'


def test_extraction_preserves_unit_error_for_scoring():
    schema = {'type':'object','properties':{'creatinine_mg_dl':{'type':['number','null'],'minimum':.2,'maximum':15}},'required':['creatinine_mg_dl'],'additionalProperties':False}
    cfg = ModelConfig('t','extraction-units','http://test/v1','')
    action = lambda arguments: response('{"creatinine_mg_dl":88.4}')
    factory = lambda **kw: FakeClient(action,**kw)
    result = call_model(cfg,[],schema,score_extraction=True,client_factory=factory)
    assert result.value['creatinine_mg_dl'] == 88.4
    with pytest.raises(ModelError):
        call_model(cfg,[],schema,client_factory=factory)


def test_real_sdk_request_with_mock_transport_without_auth():
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append((request.url.path, request.headers.get('Authorization'), body))
        payload = {'id': 'fixture', 'object': 'chat.completion', 'created': 1700000000, 'model': 'fixture-model',
                   'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '{"odpowiedz":"OK"}'}, 'finish_reason': 'stop'}],
                   'usage': {'prompt_tokens': 8, 'completion_tokens': 4, 'total_tokens': 12}}
        return httpx.Response(200, json=payload)
    def factory(**kwargs):
        return OptionalAuthOpenAI(http_client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False), **kwargs)
    cfg = ModelConfig('t', 'fixture-model', 'http://test/v1', '', timeout=10)
    result = call_model(cfg, [{'role': 'user', 'content': 'Pytanie testowe'}], TEXT_SCHEMA, client_factory=factory)
    assert result.value == {'odpowiedz': 'OK'} and result.tokens == 12
    assert requests[0][0] == '/v1/chat/completions'
    assert requests[0][1] is None
    assert requests[0][2]['response_format']['type'] == 'json_schema'


def test_label_and_reasoning_effort_from_environment(monkeypatch):
    monkeypatch.setenv('ORNITH_LABEL','Gemma 4 31B')
    monkeypatch.setenv('ORNITH_REASONING_EFFORT','minimal')
    configs = model_configs()
    assert list(configs) == ['Gemma 4 31B','Qwen']
    assert configs['Gemma 4 31B'].reasoning_effort == 'minimal' and configs['Qwen'].reasoning_effort == ''
    calls = []
    def action(arguments):
        calls.append(arguments)
        return response('<thought>{"odpowiedz":"szkic"}</thought>{"odpowiedz":"OK"}')
    factory = lambda **kw: FakeClient(action,**kw)
    cfg = ModelConfig('t','reasoning-minimal','http://test/v1','',reasoning_effort='minimal')
    assert call_model(cfg,[],TEXT_SCHEMA,client_factory=factory,bypass_cache=True).value == {'odpowiedz':'OK'}
    assert calls[0]['reasoning_effort'] == 'minimal'
