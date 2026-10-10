"""Opcjonalna integracja z zgodnym pakietem A; bez zapisu w exercises/."""
from pathlib import Path
import shutil
import pytest
from streamlit.testing.v1 import AppTest
from lab.data import dictionary, read_table, package_problem
from lab.rules import package_rules, run_rules
from lab.scoring import compare_findings

APP = Path(__file__).resolve().parent.parent
DATA = APP.parent/'exercises'/'dane'

@pytest.fixture
def package_a(tmp_path):
    problem = package_problem(DATA)
    if problem:
        pytest.skip('Opcjonalna integracja A: ' + problem)
    snapshot = tmp_path/'dane'
    try:
        shutil.copytree(DATA,snapshot)
        rule_file = DATA.parent/'walidacja'/'reguly.yaml'
        if rule_file.exists():
            folder = tmp_path/'walidacja'
            folder.mkdir()
            shutil.copy2(rule_file,folder/'reguly.yaml')
        problem = package_problem(snapshot)
        if problem:
            pytest.skip('Pakiet A zmienił się podczas kopiowania: ' + problem)
        yield snapshot
    except FileNotFoundError:
        pytest.skip('Pakiet A był odtwarzany podczas pobierania kopii do testu.')
    finally:
        if snapshot.exists(): shutil.rmtree(snapshot)
        if (tmp_path/'walidacja').exists(): shutil.rmtree(tmp_path/'walidacja')


def test_current_package_a_rule_catalog_and_traps(package_a):
    definitions = dictionary(package_a)
    frame = read_table(package_a/'rejestr_brudny.xlsx')
    rules, messages = package_rules(package_a,definitions)
    assert not messages
    assert any(r.id.startswith('pakiet:phoenix:') for r in rules)
    result = run_rules(frame,definitions,rules)
    key = read_table(package_a/'klucz_bledow.csv')
    traps = read_table(package_a/'pulapki_nie_bledy.csv')
    metrics, _, _ = compare_findings(key,{'Reguły':result},traps)
    assert metrics.iloc[0]['wykryte'] > 0
    assert metrics.iloc[0]['trafienia w pułapki'] == 0


def test_current_package_a_renders_all_tabs(monkeypatch, package_a):
    monkeypatch.setenv('DATA_DIR',str(package_a))
    at = AppTest.from_file(str(APP/'app.py'),default_timeout=60).run()
    assert not at.exception and len(at.get('tab')) == 7
    at.button(key='rules_run').click().run()
    assert not at.exception
    at.button(key='key_reveal').click().run()
    assert not at.exception
