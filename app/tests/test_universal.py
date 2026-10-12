"""Uniwersalne materiały, reguły i serwery; bez sieci zewnętrznej."""
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
import httpx
import pandas as pd
import pytest
from openai import RateLimitError
import streamlit as st
from streamlit.testing.v1 import AppTest
import lab.endpoints as endpoints
import lab.llm as llm
from lab.config import ModelConfig, model_configs
from lab.data import DICTIONARY_COLUMNS, read_table, dictionary, excel_bytes
from lab.rules import (Rule, custom_rule, available_rules, run_rules, rule_preview, rule_label,
                       import_rules, rule_summary, default_rules, package_rules)
from lab.universal import (MINIMAL_SCHEMA, own_dictionary, validate_extraction_schema, schema_fields, add_document)
from lab.prompts import TEXT_SCHEMA
from tests.test_llm import FakeClient, response

APP = Path(__file__).resolve().parent.parent / 'app.py'


def start():
    at = AppTest.from_file(str(APP), default_timeout=180).run()
    assert not at.exception
    return at


class Upload(BytesIO):
    def __init__(self, name, raw):
        super().__init__(raw)
        self.name, self.size = name, len(raw)


def inject_uploads(monkeypatch, uploads):
    original = st.file_uploader
    def uploader(*args, **kwargs):
        widget = original(*args, **kwargs)
        return uploads.get(kwargs.get('key'), widget)
    monkeypatch.setattr(st, 'file_uploader', uploader)


def http_client(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(endpoints.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    endpoints._CACHE.clear()


def test_ollama_tags_cache_fallback_and_failure(monkeypatch):
    calls = []
    mode = ['tags']
    def handler(request):
        calls.append(request)
        if mode[0] == 'tags':
            return httpx.Response(200, json={'models': [{'name': 'qwen2.5:7b'}, {'name': 'gemma3:4b'}]})
        if mode[0] == 'fallback':
            return httpx.Response(404) if request.url.path == '/api/tags' else httpx.Response(200, json={'data': [{'id': 'local'}]})
        raise httpx.ConnectError('unreachable', request=request)
    http_client(monkeypatch, handler)
    configs, note = endpoints.ollama_models('http://ollama:11434')
    assert list(configs) == ['Ollama: qwen2.5:7b', 'Ollama: gemma3:4b'] and note is None
    assert all(c.base_url == 'http://ollama:11434/v1' and not c.api_key for c in configs.values())
    assert endpoints.ollama_models('http://ollama:11434')[0] == configs and len(calls) == 1
    endpoints._CACHE['http://ollama:11434'] = (0, configs, None)
    endpoints.ollama_models('http://ollama:11434')
    assert len(calls) == 2
    endpoints._CACHE.clear()
    mode[0] = 'fallback'
    assert 'Ollama: local' in endpoints.ollama_models('http://test')[0]
    endpoints._CACHE.clear()
    mode[0] = 'failed'
    configs, note = endpoints.ollama_models('http://test')
    assert configs == {} and 'niedostępna' in note


@pytest.mark.parametrize('url', ['file:///secret', 'http://user:secret@test/v1', 'http://test?key=secret', 'http://test/#secret', 'http://test:wrong/v1', 'http://test:99999/v1'])
def test_endpoint_rejects_credentials_in_url(url):
    with pytest.raises(ValueError): endpoints.endpoint_url(url)


def test_custom_endpoint_no_key_cache_or_error_leak(monkeypatch):
    calls = []
    secret = 'fixture-secret-never-persist'
    def handler(request):
        calls.append(request)
        return httpx.Response(401, text=secret)
    http_client(monkeypatch, handler)
    with pytest.raises(ValueError) as error:
        endpoints.endpoint_models('http://test', secret)
    assert secret not in str(error.value)
    assert calls[0].url.path == '/v1/models' and calls[0].headers['Authorization'] == 'Bearer ' + secret
    assert not endpoints._CACHE


@pytest.mark.parametrize('retry_after,expected', [(None, [5, 10]), ('7', [7, 7])])
def test_429_retries_in_deadline_with_queue(monkeypatch, retry_after, expected, tmp_path):
    now, sleeps, arguments, queue = [0.0], [], [], []
    monkeypatch.setattr(llm.time, 'monotonic', lambda: now[0])
    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds
    monkeypatch.setattr(llm.time, 'sleep', sleep)
    def action(kwargs):
        arguments.append(kwargs)
        if len(arguments) <= 2:
            headers = {'Retry-After': retry_after} if retry_after else {}
            raise RateLimitError('secret-body', response=httpx.Response(429, headers=headers, request=httpx.Request('POST', 'http://test')), body={})
        return response()
    cfg = ModelConfig('t', 'rate-' + str(retry_after), 'http://test/v1', 'fixture-secret', timeout=20)
    result = llm.call_model(cfg, [], TEXT_SCHEMA, client_factory=lambda **kw: FakeClient(action), bypass_cache=True, on_queue=lambda: queue.append(True))
    assert result.value == {'odpowiedz': 'OK'} and sleeps == expected and len(queue) == 2
    assert [a['timeout'] for a in arguments] == [20, 20 - expected[0], 20 - sum(expected)]
    assert 'fixture-secret' not in ''.join(p.read_text() for p in (tmp_path / 'logs').glob('*'))
    assert not (tmp_path / 'cache').exists()


def test_429_does_not_sleep_past_deadline(monkeypatch):
    def action(kwargs):
        raise RateLimitError('busy', response=httpx.Response(429, headers={'Retry-After': '200'}, request=httpx.Request('POST', 'http://test')), body={})
    monkeypatch.setattr(llm.time, 'sleep', lambda _: pytest.fail('Przekroczony termin'))
    with pytest.raises(llm.ModelError, match='zajęty'):
        llm.call_model(ModelConfig('t', 'deadline', 'http://test/v1', '', timeout=180), [], TEXT_SCHEMA,
                       bypass_cache=True, client_factory=lambda **kw: FakeClient(action))


def test_retry_after_http_date():
    from datetime import datetime, timezone, timedelta
    from email.utils import format_datetime
    at = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True)
    exc = SimpleNamespace(response=httpx.Response(429, headers={'Retry-After': at}))
    assert 28 < llm.retry_delay(exc, 0) <= 30


def test_negation_preview_missing_and_summary():
    frame = pd.DataFrame({'patient_id': ['A', 'A', 'B', 'C'], 'x': ['-1', '2', '', 'brak']})
    definitions = own_dictionary(pd.DataFrame({'zmienna': ['x'], 'typ': ['liczba']}))
    raw = dict(kind='query', variable='x', expression='x >= 0')
    rule = custom_rule(raw, set(frame), correct=True)
    assert rule.expression == 'not (x >= 0)' and rule.description.startswith('Oznacz, gdy ')
    result = run_rules(frame, definitions, [rule])
    assert result.wiersz.tolist() == [2]
    count, preview = rule_preview(frame, definitions, rule)
    assert count == 1 and list(preview) == ['patient_id', 'x']
    assert preview.x.tolist() == ['-1']
    summary = rule_summary(result, [rule]).iloc[0]
    assert summary['oznaczone wiersze'] == summary['różni pacjenci'] == 1
    range_rule = custom_rule(dict(kind='range', variable='x', minimum=0), set(frame))
    assert 'braki' in rule_label(range_rule) and run_rules(frame, definitions, [range_rule]).wiersz.tolist() == [2]
    positive = custom_rule(dict(kind='query', variable='x', expression='x != 2'), set(frame))
    assert run_rules(frame, definitions, [positive]).wiersz.tolist() == [2]


def test_missing_rule_dependencies_skip_all_kinds(definitions):
    rules = [Rule('q', 'Q', 'query', 'patient_id', expression='x > 1'),
             Rule('a', 'A', 'age', 'birth_date', parameters={'reference_date': 'missing'}),
             Rule('c', 'C', 'chronology', 'patient_id', parameters={'kolejnosc': [['left', 'right']]}),
             Rule('r', 'R', 'range', 'absent', minimum=0)]
    frame = pd.DataFrame({'patient_id': ['A'], 'birth_date': ['2000-01-01']})
    ready, skipped = available_rules(rules, set(frame))
    assert not ready and len(skipped) == 4
    result = run_rules(frame, definitions, rules)
    assert result.empty and result.attrs['skipped_rules'] == skipped


def test_rule_import_validates_columns_safe_expression_and_roundtrip():
    frame = pd.DataFrame({'patient_id': ['A'], 'x': [-1]})
    definitions = own_dictionary(pd.DataFrame({'zmienna': ['x'], 'typ': ['liczba']}))
    rule = custom_rule(dict(kind='query', variable='x', expression='x >= 0'), set(frame), True)
    content = [rule.to_dict(), dict(kind='query', variable='x', expression="__import__('os')"), dict(kind='range', variable='missing', minimum=0)]
    ready, rejected = import_rules(json.dumps(content), frame, definitions)
    assert len(ready) == 1 and len(rejected) == 2 and ready[0].expression == rule.expression
    assert ready[0].parameters == rule.parameters and run_rules(frame, definitions, ready).wiersz.tolist() == [2]
    for content in ('{}', '[]' * 2):
        with pytest.raises(ValueError): import_rules(content, frame, definitions)


def test_dictionary_csv_xlsx_and_template():
    for content, name in [(b'zmienna;typ\nx;liczba\n', 'own.csv'), (excel_bytes(pd.DataFrame({'zmienna': ['x'], 'typ': ['liczba']})), 'own.xlsx')]:
        table = own_dictionary(read_table(BytesIO(content), name))
        assert set(DICTIONARY_COLUMNS).issubset(table) and table.iloc[0].etykieta == ''
        assert any(r.variable == 'x' for r in default_rules(table))
    for table in (pd.DataFrame({'x': [1]}), pd.DataFrame({'zmienna': ['x', 'x'], 'typ': ['tekst', 'tekst']})):
        with pytest.raises(ValueError): own_dictionary(table)


@pytest.mark.parametrize('schema', ['[]', '{}', '{', '{"type":"array","properties":{"x":{}}}',
    '{"type":"object","properties":{}}', '{"type":"object","properties":{"x":{"type":"string","minLength":1}}}',
    '{"type":"object","properties":{"x":{"format":"time"}}}', '{"type":"object","properties":{"x":{"pattern":"["}}}',
    '{"type":"object","properties":{"x":{"minimum":NaN}}}', '{"type":"object","properties":{"x":{}},"required":["y"]}'])
def test_schema_rejects_unsupported_and_invalid(schema):
    with pytest.raises(ValueError): validate_extraction_schema(schema)


def test_default_schema_supported_and_fields(fixture_dir):
    text = (fixture_dir / 'ekstrakcja_schemat.json').read_text()
    schema = validate_extraction_schema(text)
    assert schema == json.loads(text) and len(schema_fields(schema)) == 25
    assert validate_extraction_schema(json.dumps(MINIMAL_SCHEMA)) == MINIMAL_SCHEMA


def test_own_document_limits_and_utf8():
    documents = {}
    assert add_document(documents, 'own.md', 'Syntetyczny tekst') == 'własny:own.md'
    for name, text in [('a.pdf', b'x'), ('../a.txt', b'x'), ('a.txt', b'\xff'), ('a.txt', b'x' * 100001), ('a.txt', '')]:
        with pytest.raises(ValueError): add_document(documents, name, text)
    for index in range(19): add_document(documents, f'{index}.txt', b'ok')
    with pytest.raises(ValueError): add_document(documents, 'extra.txt', b'ok')
    add_document(documents, 'own.md', b'updated')
    assert len(documents) == 20


def test_ui_select_all_category_and_negation_preview(fixture_dir, definitions):
    rules, _ = package_rules(fixture_dir, definitions)
    range_keys = {f'rule:{r.id}' for r in rules if r.category == 'zakres'}
    at = start()
    at.button(key='rules_deselect_all').click().run()
    assert all(not c.value for c in at.checkbox if c.key.startswith('rule:'))
    at.button(key='rules_select:zakres').click().run()
    assert all(c.value for c in at.checkbox if c.key in range_keys)
    assert all(not c.value for c in at.checkbox if c.key.startswith('rule:') and c.key not in range_keys)
    at.button(key='rules_deselect:zakres').click().run()
    assert all(not c.value for c in at.checkbox if c.key.startswith('rule:'))
    at.button(key='rules_select_all').click().run()
    assert all(c.value for c in at.checkbox if c.key.startswith('rule:'))
    at.radio(key='custom_mode').set_value('Wyrażenie pandas query').run()
    at.selectbox(key='custom_variable').select('adt')
    at.radio(key='custom_semantics').set_value('Warunek opisuje poprawną wartość (oznacz wiersze, które go NIE spełniają)')
    at.text_input(key='custom_expression').set_value('adt == 1 or adt_months == 0').run()
    assert any('Ta reguła oznaczy 1 z 12 wierszy' in text.value for text in at.markdown)
    preview = next(d.value for d in at.dataframe if list(d.value) == ['patient_id', 'adt', 'adt_months'])
    assert len(preview) == 1
    at.button(key='custom_add').click().run()
    assert not at.exception and at.session_state['custom_rules'][0].expression.startswith('not (')
    at.button(key='rules_run').click().run()
    assert not at.exception and any('oznaczone wiersze' in d.value for d in at.dataframe)
    assert any('Wiersze bez naruszeń:' in m.value for m in at.markdown)


def test_ui_schema_edit_validation_reset_and_extraction(monkeypatch):
    calls = []
    def mock(config, messages, schema, **kwargs):
        calls.append(schema)
        return SimpleNamespace(value={'patient_id': 'PR-001', 'extra': 'test'}, elapsed=.1, cached=False)
    monkeypatch.setattr(llm, 'call_model', mock)
    at = start()
    default = at.session_state['applied_schema']
    at.text_area(key='schema_editor').set_value('{bad').run()
    at.button(key='schema_apply').click().run()
    assert at.session_state['applied_schema'] == default and any('Nie zastosowano' in e.value for e in at.error)
    schema = {'type': 'object', 'properties': {'patient_id': {'type': ['string', 'null']}, 'extra': {'type': 'string'}}, 'required': ['patient_id', 'extra']}
    at.text_area(key='schema_editor').set_value(json.dumps(schema)).run()
    at.button(key='schema_apply').click().run()
    at.button(key='extraction_run').click().run()
    assert not at.exception and calls == [schema]
    comparisons = next(d.value for d in at.dataframe if 'typ rozbieżności' in d.value)
    assert comparisons.zmienna.tolist() == ['patient_id']
    at.button(key='schema_reset').click().run()
    assert at.session_state['applied_schema'] == default and json.loads(at.text_area(key='schema_editor').value) == default


def test_ui_own_paste_upload_extraction_fake_client_and_no_cache(monkeypatch, tmp_path):
    uploads = {'documents_upload': [Upload('upload.md', b'Tekst syntetyczny') , Upload('bad.txt', b'\xff')]}
    inject_uploads(monkeypatch, uploads)
    calls = []
    original = llm.call_model
    def fake_call(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs, client_factory=lambda **kw: FakeClient(lambda a: response('{"patient_id":"SYN-001"}')))
    monkeypatch.setattr(llm, 'call_model', fake_call)
    at = start()
    at.text_area(key='schema_editor').set_value(json.dumps(MINIMAL_SCHEMA)).run()
    at.button(key='schema_apply').click().run()
    at.button(key='documents_add').click().run()
    assert 'własny:upload.md' in at.session_state['own_documents']
    assert any('UTF-8' in e.value for e in at.error)
    at.text_input(key='paste_document_name').set_value('paste.txt')
    at.text_area(key='paste_document').set_value('Wyłącznie syntetyczny dokument.').run()
    at.button(key='document_paste_add').click().run()
    assert '(własny)' in at.multiselect(key='selected_docs').options[-1]
    at.multiselect(key='selected_docs').set_value(['własny:upload.md', 'własny:paste.txt']).run()
    at.button(key='extraction_run').click().run()
    assert not at.exception and len(at.session_state['extraction_results']) == 2
    assert all(c['bypass_cache'] for c in calls) and not list((tmp_path / 'cache').glob('*'))
    assert not at.metric
    logs = ''.join(p.read_text() for p in (tmp_path / 'logs').glob('*'))
    assert 'Wyłącznie' not in logs and 'Tekst syntetyczny' not in logs


def test_ui_missing_documents_schema_and_own_registry_dictionary(monkeypatch, tmp_path, fixture_dir):
    # Kompletny rdzeń pakietu bez dokumentów, reguł i schematu ekstrakcji.
    for name in ('slownik_danych.csv', 'scenariusz.json', 'rejestr_brudny.csv'):
        (tmp_path / name).write_bytes((fixture_dir / name).read_bytes())
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    uploads = {'registry_upload': Upload('own.csv', b'patient_id;x\nSYN-001;2\nSYN-002;-1\n'),
               'dictionary_upload': Upload('own.csv', b'zmienna;typ;zakres_min\nx;liczba;0\nabsent;liczba;0\n')}
    inject_uploads(monkeypatch, uploads)
    observed = []
    def mock(config, messages, schema, **kwargs):
        observed.append((messages, kwargs))
        return SimpleNamespace(value={'podejrzenia': []}, elapsed=.1, cached=False)
    monkeypatch.setattr(llm, 'call_model', mock)
    at = start()
    assert at.session_state['applied_schema'] == MINIMAL_SCHEMA
    assert at.multiselect(key='selected_docs').options == []
    assert at.button(key='key_reveal').disabled
    at.selectbox(key='eda_variable').select('x').run()
    at.button(key='rules_run').click().run()
    assert at.session_state['rule_results'].wiersz.tolist() == [3]
    at.button(key='clinical_run').click().run()
    assert not at.exception and observed[0][1]['bypass_cache']
    payload = json.loads(observed[0][0][-1]['content'])
    assert payload['slownik'][0]['zmienna'] == 'x' and set(payload['wiersze'][0]) == {'patient_id', 'x'}
    shown = at.text_area(key='clinical_user_preview:' + at.session_state['data_signature'] + ':1:2:False').value
    assert json.loads(shown) == payload
    assert any('brakujących kolumn' in i.value for i in at.info)
    at.text_area(key='paste_document').set_value('Syntetyczny dokument').run()
    at.button(key='document_paste_add').click().run()
    assert at.multiselect(key='selected_docs').value == ['własny:dokument.txt']


def test_ui_custom_endpoint_opt_in_ollama_and_unreachable(monkeypatch):
    at = start()
    assert not any(e.label == 'Własny serwer modelu' for e in at.expander)
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://ollama')
    monkeypatch.setattr(endpoints, 'ollama_models', lambda _: ({'Ollama: local': ModelConfig('Ollama: local', 'local', 'http://ollama/v1', '')}, None))
    monkeypatch.setenv('ALLOW_CUSTOM_ENDPOINT', '1')
    at = start()
    assert 'Ollama: local' in at.selectbox(key='chosen_model').options
    monkeypatch.setattr(endpoints, 'endpoint_models', lambda url, key: ['installed'])
    at.text_input(key='endpoint_url').set_value('http://test')
    at.text_input(key='endpoint_key').set_value('fixture-secret')
    at.button(key='endpoint_fetch').click().run()
    at.button(key='endpoint_use').click().run()
    at.selectbox(key='chosen_model').select('Własny serwer').run()
    calls = []
    def mock(config, messages, schema, **kwargs):
        calls.append((config, kwargs))
        return SimpleNamespace(value={'odpowiedz': 'OK'}, elapsed=.1, cached=False)
    monkeypatch.setattr(llm, 'call_model', mock)
    at.chat_input(key='chat_question').set_value('Test').run()
    assert calls[0][0].api_key == 'fixture-secret' and calls[0][0].base_url == 'http://test/v1' and calls[0][1]['bypass_cache']
    assert 'fixture-secret' not in str([e.value for e in at.markdown])
    monkeypatch.setattr(endpoints, 'ollama_models', lambda _: ({}, 'Ollama jest niedostępna.'))
    at = start()
    assert len([e for e in at.info if 'Ollama' in e.value]) == 1
    assert {'Ornith', 'Qwen'}.issubset(at.selectbox(key='chosen_model').options)


def test_ui_rule_import_reports_rejections(monkeypatch):
    raw = [dict(kind='range', variable='psa_dx_ng_ml', minimum=0), dict(kind='range', variable='absent', minimum=0)]
    inject_uploads(monkeypatch, {'rules_import': Upload('own.json', json.dumps(raw).encode())})
    at = start()
    at.button(key='rules_import_apply').click().run()
    assert not at.exception and len(at.session_state['custom_rules']) == 1
    assert any('Odrzucono:' in error.value for error in at.error)


def test_compose_and_env_documentation():
    import yaml
    app = APP.parent
    compose = yaml.safe_load((app / 'docker-compose.yml').read_text())
    assert compose['services']['app']['environment']['OLLAMA_BASE_URL'] == 'http://ollama:11434'
    assert compose['services']['app']['environment']['ALLOW_CUSTOM_ENDPOINT'] == '1'
    assert any(v.endswith(':/data:ro') for v in compose['services']['app']['volumes'])
    assert compose['services']['ollama']['image'] == 'ollama/ollama'
    assert 'ollama-models' in compose['volumes']
    for name in ('OLLAMA_BASE_URL', 'ALLOW_CUSTOM_ENDPOINT'):
        assert name in (app / '.env.example').read_text() and name in (app / 'README.md').read_text()



def test_extraction_fields_without_key_are_not_scored(fixture_dir):
    from lab.scoring import compare_extraction
    gold = read_table(fixture_dir / 'ekstrakcja_klucz.csv')
    result = {'DOK-01.txt': {'patient_id': 'PR-001', 'extra': 'synthetic'}}
    comparisons, per_doc, accuracy = compare_extraction(result, gold, ['patient_id', 'extra'])
    assert comparisons.zmienna.tolist() == ['patient_id'] and per_doc.iloc[0]['pola'] == 1
    comparisons, per_doc, accuracy = compare_extraction(result, gold, ['extra'])
    assert comparisons.empty and accuracy is None and per_doc.iloc[0]['pola'] == 0


def test_ui_empty_data_dir_uses_minimal_schema(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path / 'absent'))
    at = start()
    assert not at.exception and at.session_state['applied_schema'] == MINIMAL_SCHEMA
    assert at.multiselect(key='selected_docs').options == []
    at.text_area(key='paste_document').set_value('Syntetyczny tekst').run()
    at.button(key='document_paste_add').click().run()
    assert at.multiselect(key='selected_docs').value == ['własny:dokument.txt']



def test_rule_preview_ten_rows_and_patient_summary():
    frame = pd.DataFrame({'patient_id': ['SYN-001'] * 12, 'x': [-1] * 12})
    definitions = own_dictionary(pd.DataFrame({'zmienna': ['x'], 'typ': ['liczba']}))
    rule = custom_rule(dict(kind='range', variable='x', minimum=0), set(frame))
    count, preview = rule_preview(frame, definitions, rule)
    assert count == 12 and len(preview) == 10
    summary = rule_summary(run_rules(frame, definitions, [rule]), [rule]).iloc[0]
    assert summary['oznaczone wiersze'] == 12 and summary['różni pacjenci'] == 1



def test_import_ids_remain_unique_after_rejections():
    frame = pd.DataFrame({'x': [-1]})
    definitions = own_dictionary(pd.DataFrame({'zmienna': ['x'], 'typ': ['liczba']}))
    content = json.dumps([{'kind': 'range', 'variable': 'absent', 'minimum': 0},
                          {'kind': 'range', 'variable': 'x', 'minimum': 0}])
    first, _ = import_rules(content, frame, definitions)
    second, _ = import_rules(content, frame, definitions, len(first))
    assert first[0].id != second[0].id



def test_ui_unknown_registry_columns_support_eda_and_skip_rules(monkeypatch):
    uploads = {}
    inject_uploads(monkeypatch, uploads)
    calls = []
    def mock(config, messages, schema, **kwargs):
        calls.append((messages, kwargs))
        return SimpleNamespace(value={'odpowiedz': 'Sprawdź wartości w źródle.'}, elapsed=.1, cached=False)
    monkeypatch.setattr(llm, 'call_model', mock)
    at = start()
    uploads['registry_upload'] = Upload('own.csv', b'patient_id;marker\nSYN-001;1\nSYN-002;3\n')
    at.run()
    assert not at.exception and at.number_input(key='clinical_last').value == 2
    at.selectbox(key='eda_variable').select('marker').run()
    at.button(key='eda_ai').click().run()
    at.button(key='rules_run').click().run()
    assert not at.exception and calls[0][1]['bypass_cache']
    assert json.loads(calls[0][0][-1]['content'])['zmienna'] == 'marker'
    assert any('brakujących kolumn' in i.value for i in at.info)



@pytest.mark.parametrize('actual', [['PR-001'], {'id': 'PR-001'}])
def test_extraction_collections_against_scalar_key(actual):
    from lab.scoring import compare_extraction, null_value, discrepancy
    gold = pd.DataFrame({'dokument': ['DOK-01.txt'], 'patient_id': ['PR-001']})
    comparisons, per_doc, accuracy = compare_extraction({'DOK-01.txt': {'patient_id': actual}}, gold, ['patient_id'])
    assert not null_value(actual) and not comparisons.iloc[0]['zgodność'] and accuracy == 0
    assert comparisons.iloc[0]['typ rozbieżności'] == 'błędna wartość'
    assert discrepancy(actual, None, 'patient_id') == 'halucynacja'


def test_ui_array_field_scoring_does_not_crash(monkeypatch):
    def mock(config, messages, schema, **kwargs):
        return SimpleNamespace(value={'patient_id': ['PR-001']}, elapsed=.1, cached=False)
    monkeypatch.setattr(llm, 'call_model', mock)
    at = start()
    schema = {'type': 'object', 'properties': {'patient_id': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['patient_id']}
    at.text_area(key='schema_editor').set_value(json.dumps(schema)).run()
    at.button(key='schema_apply').click().run()
    at.button(key='extraction_run').click().run()
    assert not at.exception and any(m.value == '0.0%' for m in at.metric)
