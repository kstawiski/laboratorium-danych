"""Siedem zakładek i działania użytkownika; bez połączeń z modelem."""
from pathlib import Path
import json
from types import SimpleNamespace
import pandas as pd
from streamlit.testing.v1 import AppTest
import lab.llm
from lab.scoring import null_value
from lab.prompts import TEXT_SCHEMA
from lab.data import read_table

APP = Path(__file__).resolve().parent.parent / 'app.py'


def start():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    return at


def test_all_tabs_render_without_model(monkeypatch):
    def forbidden(*a,**kw):
        raise AssertionError('Model nie powinien być wywołany przy otwieraniu aplikacji')
    monkeypatch.setattr(lab.llm, 'call_model', forbidden)
    at = start()
    assert len(at.get('tab')) == 7
    assert at.session_state['group'] == ''
    at.text_input(key='group').set_value('Grupa testowa').run()
    assert at.session_state['group'] == 'Grupa testowa'
    at.selectbox(key='eda_variable').select('rt_dose_gy').run()
    assert not at.exception
    at.button(key='rules_run').click().run()
    assert not at.exception
    assert len(at.session_state['rule_results']) > 10
    assert 'key_shown' not in at.session_state or not at.session_state['key_shown']
    at.button(key='key_reveal').click().run()
    assert not at.exception and at.session_state['key_shown']


def test_mocked_ai_flows(monkeypatch, fixture_dir):
    calls = []
    gold = read_table(fixture_dir/'ekstrakcja_klucz.csv')
    schema = json.loads((fixture_dir/'ekstrakcja_schemat.json').read_text())
    def mock(config, messages, requested_schema, **kwargs):
        calls.append(kwargs['tab'])
        if kwargs['tab'] == 'AI: ekstrakcja z dokumentów':
            # DOK-01 domyślnie, z prawidłowymi typami JSON.
            row = gold.iloc[0]
            value = {}
            for field,spec in schema['properties'].items():
                raw = row[field]
                types = spec['type']
                value[field] = None if null_value(raw) else int(float(raw)) if 'integer' in types else float(raw) if 'number' in types else raw
        elif kwargs['tab'] == 'AI: wiarygodność kliniczna':
            batch = json.loads(messages[-1]['content'])['wiersze']
            value = {'podejrzenia':[{'patient_id':'PR-001','zmienna':'rt_dose_gy','wartosc':780,'problem':'Dawka >100 Gy', 'powaga':'krytyczne', 'sugerowane_dzialanie':'zapytanie'}] if any(row['patient_id'] == 'PR-001' for row in batch) else []}
        elif kwargs['tab'] == 'Reguły walidacyjne':
            value = {'reguly':[{'id':'ai1','description':'Dawka poza 1–100','kind':'range','variable':'rt_dose_gy','minimum':0,'maximum':100,'expression':'','values':[]}]}
        else:
            value = {'odpowiedz':'Komentarz testowy'}
        return SimpleNamespace(value=value, tokens=10, elapsed=.1, cached=False, json_mode='mock')
    monkeypatch.setattr(lab.llm, 'call_model', mock)
    at = start()
    at.selectbox(key='eda_variable').select('rt_dose_gy').run()
    at.button(key='eda_ai').click().run()
    assert not at.exception and at.session_state['eda_comment']['answer'] == 'Komentarz testowy'
    at.button(key='rules_ai').click().run()
    assert not at.exception and len(at.session_state['proposed_rules']) == 1
    # Dodanie propozycji jest osobnym działaniem.
    assert 'custom_rules' not in at.session_state or not at.session_state['custom_rules']
    at.multiselect(key='accepted_rules').select(0).run()
    at.button(key='rules_accept').click().run()
    assert not at.exception and len(at.session_state['custom_rules']) == 1
    at.button(key='extraction_run').click().run()
    assert not at.exception
    assert 'DOK-01.txt' in at.session_state['extraction_results']
    assert any(m.value == '100.0%' for m in at.metric)
    at.button(key='clinical_run').click().run()
    assert not at.exception and len(at.session_state['clinical_results']) == 1
    at.text_area(key='findings_paste').set_value('patient_id;zmienna;problem;decyzja\npr 001;rt_dose_gy;780 Gy;zapytanie').run()
    at.button(key='findings_load').click().run()
    assert not at.exception and len(at.session_state['group_findings']) == 1
    at.button(key='key_reveal').click().run()
    assert not at.exception
    at.chat_input(key='chat_question').set_value('Napisz formułę Excela').run()
    assert not at.exception
    assert at.session_state['chat_history'][-1]['content'] == 'Komentarz testowy'
    assert set(calls) == {'EDA', 'Reguły walidacyjne', 'AI: ekstrakcja z dokumentów', 'AI: wiarygodność kliniczna', 'Czat z modelem'}


def test_model_failure_is_visible_and_does_not_crash(monkeypatch):
    def failed(*a,**kw): raise lab.llm.ModelError('Serwer modelu jest zajęty, spróbuj za chwilę.')
    monkeypatch.setattr(lab.llm,'call_model',failed)
    at = start()
    at.button(key='extraction_run').click().run()
    assert not at.exception
    assert any('Serwer modelu jest zajęty' in e.value for e in at.error)
    assert at.session_state['extraction_failures'] == ['DOK-01.txt']


def test_custom_query_is_addable_and_key_stays_hidden():
    at = start()
    at.radio(key='custom_mode').set_value('Wyrażenie pandas query')
    at.selectbox(key='custom_variable').select('adt')
    at.text_input(key='custom_expression').set_value('adt == 0 and adt_months > 0')
    at.button(key='custom_add').click().run()
    assert not at.exception
    assert len(at.session_state['custom_rules']) == 1
    at.button(key='rules_run').click().run()
    assert not at.exception
    assert any('Własna:' in r for r in at.session_state['rule_results']['regula'])
    assert 'key_shown' not in at.session_state or not at.session_state['key_shown']


def test_incompatible_data_dir_shows_warning_and_uses_fixture(monkeypatch, tmp_path):
    pd.DataFrame({'zmienna':['patient_id','psa_dx_ng_ml'],'typ':['tekst','liczba']}).to_csv(tmp_path/'slownik_danych.csv',index=False)
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    def forbidden(*a,**kw): raise AssertionError('Brak uprawnienia do wywołania modelu w tej próbie')
    monkeypatch.setattr(lab.llm,'call_model',forbidden)
    at = start()
    assert len(at.get('tab')) == 7
    assert any('Nie można odczytać pakietu DATA_DIR' in item.value for item in at.warning)
    assert any('fixture' in item.value for item in at.warning)
    assert len(at.multiselect(key='selected_docs').options) == 2


def test_document_preview_follows_selected_document(fixture_dir):
    at = start()
    at.multiselect(key='selected_docs').set_value(['DOK-01.txt', 'DOK-02.txt']).run()
    def shown():
        return next(t.value for t in at.text_area if t.label == 'Dokument syntetyczny')
    texts = {n: (fixture_dir / 'dokumenty' / n).read_text(encoding='utf-8') for n in ('DOK-01.txt', 'DOK-02.txt')}
    assert texts['DOK-01.txt'] != texts['DOK-02.txt']
    assert shown() == texts['DOK-01.txt']
    at.selectbox(key='preview_doc').select('DOK-02.txt').run()
    assert not at.exception
    assert shown() == texts['DOK-02.txt']
    at.selectbox(key='preview_doc').select('DOK-01.txt').run()
    assert shown() == texts['DOK-01.txt']


def test_comparison_uses_ai_range_and_ignores_kept_values(monkeypatch, fixture_dir):
    def mock(config, messages, requested_schema, **kwargs):
        batch = json.loads(messages[-1]['content'])['wiersze']
        found = [{'patient_id': 'PR-001', 'zmienna': 'rt_dose_gy', 'wartosc': 780, 'problem': 'Dawka >100 Gy',
                  'powaga': 'krytyczne', 'sugerowane_dzialanie': 'zapytanie'}] if any(r['patient_id'] == 'PR-001' for r in batch) else []
        return SimpleNamespace(value={'podejrzenia': found}, tokens=10, elapsed=.1, cached=False, json_mode='mock')
    monkeypatch.setattr(lab.llm, 'call_model', mock)
    key = read_table(fixture_dir / 'klucz_bledow.csv')
    in_range = int((pd.to_numeric(key['wiersz_excel']) - 1).between(1, 3).sum())
    assert 0 < in_range < len(key)
    at = start()
    at.number_input(key='clinical_last').set_value(3).run()
    at.button(key='clinical_run').click().run()
    assert at.session_state['clinical_range'] == (1, 3)
    at.text_area(key='findings_paste').set_value(
        'patient_id;zmienna;problem;decyzja\nPR-001;rt_dose_gy;780 Gy;zapytanie do ośrodka\n'
        'PR-002;psa_dx_ng_ml;dziwne PSA;pozostaw bez zmiany\nPR-019;sex;spoza zakresu;napraw wg słownika').run()
    at.button(key='findings_load').click().run()
    at.button(key='key_reveal').click().run()
    assert not at.exception
    metrics = next(d.value for d in at.dataframe if 'źródło' in d.value.columns).set_index('źródło')
    assert {int(v) for v in metrics['wszystkie błędy']} == {in_range}
    assert int(metrics.loc['AI', 'wykryte']) == 1 and int(metrics.loc['Grupa', 'wykryte']) == 1
    assert int(metrics.loc['Grupa', 'fałszywe alarmy']) == 0
    kept = next(d.value for d in at.dataframe if 'ocena decyzji „pozostaw bez zmiany”' in d.value.columns)
    assert kept['patient_id'].tolist() == ['PR-002']


def test_default_extraction_prompt_can_be_restored():
    at = start()
    default = at.text_area(key='extraction_prompt').value
    at.text_area(key='extraction_prompt').set_value(default + '\nDodatkowa zasada.').run()
    assert at.text_area(key='extraction_prompt').value.endswith('Dodatkowa zasada.')
    at.button(key='extraction_prompt_reset').click().run()
    assert not at.exception
    assert at.text_area(key='extraction_prompt').value == default
