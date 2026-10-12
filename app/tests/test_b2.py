"""Wymagania B2: routing, limity, trwały cache i identyczność prewarm/UI."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
import json
import os
import subprocess
import sys
import httpx
import pytest
from openai import APIConnectionError
from streamlit.testing.v1 import AppTest
from lab.config import ModelConfig, model_configs, cache_dir
from lab.data import read_table, dictionary, scenario, extraction_prompt, extraction_schema, registry_file
from lab.jobs import default_jobs, extraction_job, clinical_jobs
from lab.llm import call_model, prepared_messages, _cache_key, _SEMAPHORES, _SERVER_SEMAPHORES, _ACTIVE, _INFLIGHT
from lab.prompts import TEXT_SCHEMA
from prewarm_cache import run_prewarm
from tests.test_llm import FakeClient, response

@pytest.fixture(autouse=True)
def clear_limits():
    _SEMAPHORES.clear(); _SERVER_SEMAPHORES.clear(); _ACTIVE.clear(); _INFLIGHT.clear()


def test_url_list_priority_and_single_url_compatibility(monkeypatch):
    monkeypatch.setenv('ORNITH_BASE_URL','http://single/v1')
    assert model_configs()['Ornith'].servers == ('http://single/v1',)
    monkeypatch.setenv('ORNITH_BASE_URLS',' http://first/v1/,http://second/v1, http://first/v1 ')
    cfg = model_configs()['Ornith']
    assert cfg.servers == ('http://first/v1','http://second/v1')
    assert cfg.concurrency == 6 and cfg.per_server_concurrency == 4
    monkeypatch.setenv('ORNITH_MAX_CONCURRENCY_PER_SERVER','2')
    assert model_configs()['Ornith'].per_server_concurrency == 2


def test_connection_retries_once_on_distinct_server():
    servers, calls = [], []
    cfg = ModelConfig('Ornith','retry','http://one/v1','',base_urls=('http://one/v1','http://two/v1','http://three/v1'))
    def factory(**kwargs):
        servers.append(kwargs['base_url'])
        def action(arguments):
            calls.append(arguments)
            if kwargs['base_url'] == 'http://one/v1':
                raise APIConnectionError(request=httpx.Request('POST','http://one/v1'))
            return response()
        return FakeClient(action)
    assert call_model(cfg,[],TEXT_SCHEMA,client_factory=factory,max_tokens=900).value == {'odpowiedz':'OK'}
    assert servers == ['http://one/v1','http://two/v1']
    assert all(c['max_tokens'] == 900 for c in calls)
    assert all(not any(k in c for k in ['reasoning_effort','enable_thinking','extra_body']) for c in calls)
    assert all(n == 0 for n in _ACTIVE.values())
    def failing(**kwargs):
        servers.append(kwargs['base_url'])
        def action(arguments): raise APIConnectionError(request=httpx.Request('POST',kwargs['base_url']))
        return FakeClient(action)
    from lab.llm import ModelError
    servers.clear()
    with pytest.raises(ModelError,match='drugi model'):
        call_model(cfg,[{'role':'user','content':'inne'}],TEXT_SCHEMA,client_factory=failing)
    assert len(servers) == len(set(servers)) == 2

@pytest.mark.parametrize('per_server,expected',[(2,4),(4,6)])
def test_server_limits_and_global_six(per_server,expected):
    lock, release, saturated, queued = Lock(), Event(), Event(), Event()
    active = {'http://a/v1':0,'http://b/v1':0}
    peaks, total_peak = active.copy(), 0
    cfg = ModelConfig('Ornith',f'parallel-{per_server}','http://a/v1','',timeout=10,
                      base_urls=tuple(active),per_server_concurrency=per_server)
    def factory(**kwargs):
        url = kwargs['base_url']
        def action(arguments):
            nonlocal total_peak
            with lock:
                active[url] += 1
                peaks[url] = max(peaks[url],active[url])
                total_peak = max(total_peak,sum(active.values()))
                if sum(active.values()) == expected: saturated.set()
            try:
                assert release.wait(6)
                return response()
            finally:
                with lock: active[url] -= 1
        return FakeClient(action)
    def job(i):
        return call_model(cfg,[{'role':'user','content':str(i)}],TEXT_SCHEMA,client_factory=factory,on_queue=queued.set)
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = [pool.submit(job,i) for i in range(8)]
        try:
            assert saturated.wait(4)
            assert queued.wait(2)
            assert max(active.values()) - min(active.values()) <= 1
        finally:
            release.set()
        assert all(j.result().value == {'odpowiedz':'OK'} for j in jobs)
    assert total_peak == expected and max(peaks.values()) <= per_server


def test_cache_survives_process_and_ignores_endpoint(tmp_path):
    calls = []
    cfg = ModelConfig('t','persist','http://one/v1','')
    factory = lambda **kw: FakeClient(lambda a:(calls.append(a) or response()))
    messages = [{'role':'user','content':'PRIVATE_PROMPT_NOT_ON_DISK'}]
    first = call_model(cfg,messages,TEXT_SCHEMA,client_factory=factory)
    code = '''from lab.config import ModelConfig
from lab.llm import call_model
from lab.prompts import TEXT_SCHEMA
cfg=ModelConfig('t','persist','http://other/v1','')
def forbidden(**kwargs): raise AssertionError('No model call on cache hit')
r=call_model(cfg,[{'role':'user','content':'PRIVATE_PROMPT_NOT_ON_DISK'}],TEXT_SCHEMA,client_factory=forbidden)
assert r.cached and r.value == {'odpowiedz':'OK'}
print('disk-cache-hit')
'''
    result = subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parent.parent,
                            env=os.environ.copy(),capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'disk-cache-hit'
    raw = next(cache_dir().glob('*.json')).read_text()
    assert 'PRIVATE_PROMPT' not in raw and 'http://' not in raw
    call_model(cfg,messages,TEXT_SCHEMA,max_tokens=701,client_factory=factory)
    assert len(calls) == 2
    assert not list(cache_dir().glob('*.tmp'))


def test_identical_requests_share_inflight_result():
    release, entered, queued = Event(), Event(), Event()
    calls = []
    def action(arguments):
        calls.append(arguments); entered.set()
        assert release.wait(5)
        return response()
    cfg = ModelConfig('t','single-flight','http://test/v1','',timeout=10)
    def job(): return call_model(cfg,[],TEXT_SCHEMA,client_factory=lambda **kw:FakeClient(action),on_queue=queued.set)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(job)
        assert entered.wait(3)
        others = [pool.submit(job) for _ in range(2)]
        try: assert queued.wait(3)
        finally: release.set()
        results = [first.result()] + [j.result() for j in others]
    assert len(calls) == 1 and sum(r.cached for r in results) == 2


def test_prewarm_matches_ui_calls(monkeypatch,fixture_dir):
    import lab.llm
    from types import SimpleNamespace
    observed = []
    def mock(config,messages,schema,**kwargs):
        observed.append((messages,schema,kwargs['max_tokens']))
        if kwargs['score_extraction']:
            values = {name:None for name in schema['properties']}
        else: values = {'podejrzenia':[]}
        return SimpleNamespace(value=values,tokens=0,elapsed=.01,cached=True)
    monkeypatch.setattr(lab.llm,'call_model',mock)
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent/'app.py'),default_timeout=60).run()
    assert not at.exception
    at.multiselect(key='selected_docs').set_value(['DOK-01.txt','DOK-02.txt']).run()
    at.button(key='extraction_run').click().run()
    at.button(key='clinical_run').click().run()
    assert not at.exception
    defaults = [(j.messages,j.schema,j.max_tokens) for j in default_jobs(fixture_dir)]
    assert observed == defaults
    assert run_prewarm(fixture_dir,ModelConfig('t','fixture','http://test/v1',''),caller=mock) == []
    assert observed[len(defaults):] == defaults


def test_real_package_prewarm_plan_without_model():
    path = Path(__file__).resolve().parent.parent.parent/'exercises'/'dane'
    if not path.exists(): pytest.skip('Zewnętrzny pakiet opcjonalny.')
    jobs = default_jobs(path)
    assert len(jobs) == 72  # 60 dokumentów, 12 paczek po 10 wierszy.
    assert sum(j.score_extraction for j in jobs) == 60
    clinical = [j for j in jobs if not j.score_extraction]
    assert all(len(json.loads(j.messages[-1]['content'])['wiersze']) == 10 for j in clinical)
    assert all(j.max_tokens == 900 for j in clinical)
    assert clinical[-1].name == 'wiersze 111–120'
    assert all('notes' not in row for j in clinical for row in json.loads(j.messages[-1]['content'])['wiersze'])


def test_clinical_json_is_bounded():
    from lab.prompts import SUSPICION_SCHEMA
    from lab.llm import validate_json, ModelError
    item = dict(patient_id='PR-001',zmienna='rt_dose_gy',wartosc=780,
                problem='Dawka przekracza zakres protokołu.',powaga='krytyczne',sugerowane_dzialanie='zapytanie')
    validate_json({'podejrzenia':[item]},SUSPICION_SCHEMA)
    # Decyzja integratora (próba generalna 2026-10-10): limity liczby i długości są w poleceniu,
    # ale walidacja ich nie egzekwuje, bo odrzucenie całej paczki psuło ćwiczenie (4/12 paczek).
    validate_json({'podejrzenia':[item]*9},SUSPICION_SCHEMA)
    validate_json({'podejrzenia':[dict(item,problem=' '.join(['słowo']*16))]},SUSPICION_SCHEMA)
    with pytest.raises(ModelError): validate_json({'podejrzenia':[dict(item,powaga='inne')]},SUSPICION_SCHEMA)
