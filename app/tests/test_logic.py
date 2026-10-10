import json
from io import BytesIO, StringIO
import math
import pandas as pd
import pytest
from lab.analysis import normalize_id, is_missing, missing_codes, numeric_value, outliers, eda_payload, describe
from lab.data import read_table, dictionary, excel_bytes, document_zip, id_constraints, conversion_factors, scenario
from lab.rules import default_rules, run_rules, query_mask, Rule, package_rules, validate_rule
from lab.scoring import compare_findings, compare_extraction, discrepancy
from lab.llm import parse_json, validate_json, ModelError

@pytest.mark.parametrize('value,expected', [(' pr 014 ','PR-014'),('pr-1','PR-001'),('PR_120','PR-120'),('AB 12','AB-012'),('00000000001','00000000001'),(None,''),('', '')])
def test_id_normalization(value, expected):
    assert normalize_id(value) == expected

@pytest.mark.parametrize('value', ['', None, float('nan'), 'brak', ' ND ', 'b.d.', '-', 999, 999.0, '-9'])
def test_hidden_missing(value):
    assert is_missing(value)


def test_dictionary_missing_codes_preserve_real_number():
    assert not is_missing(999, missing_codes('brak;nd;-9'))
    assert is_missing(999, missing_codes('pusta komórka; w ekstrakcji null'))
    assert numeric_value('36,25 Gy') == 36.25
    assert math.isnan(numeric_value('<0,01'))
    assert math.isnan(numeric_value('ok. 0,2'))


def test_io_preserves_dirty_tokens_and_downloads(fixture_dir):
    csv = read_table(fixture_dir / 'rejestr_brudny.csv')
    xlsx = read_table(fixture_dir / 'rejestr_brudny.xlsx')
    assert csv.at[2, 'creatinine_mg_dl'] == xlsx.at[2, 'creatinine_mg_dl'] == '88,4'
    assert list(csv) == list(xlsx)
    assert len(read_table(BytesIO(excel_bytes(csv)), 'test.xlsx')) == 12
    import zipfile
    with zipfile.ZipFile(BytesIO(document_zip(fixture_dir))) as z:
        assert z.namelist() == ['DOK-01.txt','DOK-02.txt']
    pasted = read_table(StringIO('patient_id\tzmienna\tproblem\nPR-001\trt_dose_gy\tzakres\n'), 'test.csv')
    assert pasted.iloc[0].zmienna == 'rt_dose_gy'


def test_eda_outliers_and_privacy(dirty, definitions):
    spec = definitions.set_index('zmienna').loc['rt_dose_gy'].to_dict()
    flagged = outliers(dirty, 'rt_dose_gy', spec)
    assert flagged.loc[flagged.patient_id == 'PR-001', 'poza zakresem'].all()
    assert flagged.loc[flagged.patient_id == 'PR-001', 'wiersz'].iloc[0] == 2
    payload = eda_payload(dirty, 'rt_dose_gy', spec)
    assert set(payload) == {'zmienna','jednostka','statystyki','odstajace'}
    encoded = json.dumps(payload)
    assert 'patient_id' not in encoded and 'PR-' not in encoded and 'notes' not in encoded
    summary = describe(dirty, definitions).set_index('zmienna')
    assert summary.at['weight_kg','ukryte braki'] == 1


def test_package_rules_find_known_errors_and_preserve_traps(fixture_dir, dirty, definitions):
    rules, notes = package_rules(fixture_dir,definitions)
    assert not notes
    violations = run_rules(dirty,definitions,rules)
    pairs = set(zip(violations.patient_id,violations.zmienna))
    for pair in [('PR-001','rt_dose_gy'),('PR-003','creatinine_mg_dl'),('PR-004','isup_grade'),('PR-005','psa_last_date'),('PR-005','death'),('PR-010','notes'),('PR-102','bcr_phoenix')]:
        assert pair in pairs
    assert not any(p == 'PR-008' for p,v in pairs)
    clean = read_table(fixture_dir/'rejestr_czysty.csv')
    assert run_rules(clean,definitions,rules).empty


def test_duplicate_detection_excludes_new_id(dirty, definitions):
    frame = dirty.iloc[:2].copy()
    frame.iloc[1] = frame.iloc[0]
    frame.at[1,'patient_id'] = 'PR-099'
    result = run_rules(frame,definitions,[Rule('dup','Powtórzenie','duplicate','patient_id')])
    assert result.patient_id.tolist() == ['PR-099']


def test_phoenix_boundary_and_invalid_inputs(fixture_dir,definitions):
    frame = pd.DataFrame({'patient_id':['PR-001','PR-002','PR-003','PR-004'],
        'psa_nadir_ng_ml':[.2,.2,.2,.2], 'psa_last_ng_ml':[2.19,2.2,2.21,-1], 'bcr_phoenix':[0,0,1,1]})
    rules,_ = package_rules(fixture_dir,definitions)
    result = run_rules(frame,definitions,[r for r in rules if ':phoenix:' in r.id])
    assert result.patient_id.tolist() == ['PR-002']


def test_safe_queries_and_custom_range(dirty,definitions):
    rule = Rule('own','ADT','query','adt',expression='adt == 0 and adt_months > 0')
    assert run_rules(dirty,definitions,[rule]).patient_id.tolist() == ['PR-009']
    frame = pd.DataFrame({'x':[1,2,3]})
    assert query_mask(frame,'x < 2 or x > 2').tolist() == [True,False,True]
    assert query_mask(frame,'not (x == 2)').tolist() == [True,False,True]
    assert query_mask(frame,'1 < x < 3').tolist() == [False,True,False]
    assert query_mask(frame,'x == 1 | x == 3').tolist() == [True,False,True]
    validate_rule({'kind':'query','variable':'x','expression':"x == 'a'"},{'x'})

@pytest.mark.parametrize('expression', ["__import__('os').system('id')", 'x.sum() > 0', 'x.__class__', 'x[0] > 0', '@secret > 0', 'x ** 999999999 > 0'])
def test_queries_reject_code(expression):
    for package in [False,True]:
        with pytest.raises(ValueError): query_mask(pd.DataFrame({'x':[1,2]}),expression,package=package)


def test_arbitrary_scenario_rules_and_id_range(tmp_path):
    definitions = pd.DataFrame([dict(zmienna='patient_id',typ='tekst',regula_walidacyjna='XY-010..XY-012'),
                                dict(zmienna='marker',typ='liczba',zakres_min=0,zakres_max=3)])
    (tmp_path/'reguly.yaml').write_text('reguly:\n - id: dodatkowa\n   opis: Marker\n   typ: zakres\n   zmienna: marker\n   min: 0\n   max: 3\n',encoding='utf-8')
    rules,messages = package_rules(tmp_path,definitions)
    assert not messages and len(rules) == 1
    frame = pd.DataFrame({'patient_id':['XY-009','XY-010','XY-013'],'marker':[1,2,4]})
    assert run_rules(frame,definitions,rules).patient_id.tolist() == ['XY-013']
    result = run_rules(frame,definitions,[Rule('id','Format','id','patient_id')])
    assert result.patient_id.tolist() == ['XY-009','XY-013']
    empty = pd.DataFrame({'zmienna':['patient_id'],'typ':['tekst']})
    assert id_constraints(empty,{'patient_id_pattern':'ZZ-[0-9]{2}'})['pattern'] == 'ZZ-[0-9]{2}'


def test_metrics_deduplicate_and_count_traps():
    key = pd.DataFrame({'patient_id_w_pliku':['PR-001','PR-002','PR-002'], 'zmienna':['sex','rt_dose_gy','adt']})
    source = pd.DataFrame({'patient_id':['pr 001','PR-001','PR-002','PR-003'], 'zmienna':['sex','sex','adt','sex']})
    traps = pd.DataFrame({'patient_id':['PR-003'], 'zmienna':['sex']})
    metrics,caught,false = compare_findings(key,{'Grupa':source},traps)
    assert metrics.iloc[0]['wykryte'] == 2
    assert metrics.iloc[0]['czułość %'] == pytest.approx(200/3)
    assert metrics.iloc[0]['precyzja %'] == pytest.approx(200/3)
    assert metrics.iloc[0]['fałszywe alarmy'] == metrics.iloc[0]['trafienia w pułapki'] == 1
    assert caught.Grupa.tolist() == [True,False,True]
    assert false.iloc[0]['pułapka (poprawna wartość)']


def test_metrics_empty_is_undefined():
    key = pd.DataFrame({'patient_id_w_pliku':['PR-001'], 'zmienna':['sex']})
    result,_,_ = compare_findings(key,{'Brak':pd.DataFrame()})
    assert result.iloc[0]['czułość %'] == 0 and result.iloc[0]['precyzja %'] is None

@pytest.mark.parametrize('text,expected', [('{"x":1}',{'x':1}),('Oto wynik:\n```json\n{"x":1}\n```',{'x':1}),
    ('<think>{"przyklad":0}</think>{"x":1}',{'x':1}),('[{"x":1},]',[{'x':1}]),('{"x":1,}',{'x':1}),
    ('{"x":"przecinek,} w tekście",}',{'x':'przecinek,} w tekście'})])
def test_tolerant_json(text,expected): assert parse_json(text) == expected

@pytest.mark.parametrize('text', ['brak odpowiedzi', '{"x": NaN}', '{"x":', 'null'])
def test_invalid_json(text):
    with pytest.raises(ModelError): parse_json(text)


def test_schema_rejects_missing_wrong_types_and_long_arrays():
    schema = {'type':'object','properties':{'x':{'type':['number','null']}},'required':['x'],'additionalProperties':False}
    validate_json({'x':None},schema)
    for value in ({},{'x':'1'},{'x':True},{'x':1,'secret':2}):
        with pytest.raises(ModelError): validate_json(value,schema)
    with pytest.raises(ModelError): validate_json([1,2],{'type':'array','maxItems':1})


def test_extraction_metrics_and_unit_conversions(fixture_dir, definitions):
    gold = read_table(fixture_dir/'ekstrakcja_klucz.csv')
    schema = json.loads((fixture_dir/'ekstrakcja_schemat.json').read_text())
    fields = list(schema['properties'])
    result = {k:None if str(gold.iloc[0][k]) == '' else gold.iloc[0][k] for k in fields}
    result.update(creatinine_mg_dl=88.4,ct_stage=None)
    factors = conversion_factors(definitions)
    comparisons,per_doc,accuracy = compare_extraction({'DOK-01.txt':result},gold,fields,factors)
    assert accuracy == pytest.approx(100*23/25)
    assert comparisons.set_index('zmienna').at['creatinine_mg_dl','typ rozbieżności'] == 'błąd jednostki'
    assert comparisons.set_index('zmienna').at['ct_stage','typ rozbieżności'] == 'pominięcie'
    assert discrepancy(8.4,13.54,'hemoglobin_g_dl',factors) == 'błąd jednostki'
    assert discrepancy(0,None,'diabetes') == 'halucynacja'


def test_empty_csv_has_readable_error():
    with pytest.raises(ValueError,match='Plik CSV jest pusty'): read_table(StringIO(''),'pusty.csv')


def test_metadata_fallback_for_bounds_and_id(tmp_path):
    pd.DataFrame([dict(zmienna='patient_id',typ='tekst'),dict(zmienna='marker',typ='liczba')]).to_csv(tmp_path/'slownik_danych.csv',index=False)
    metadata = {'nazwa':'Inny scenariusz','zakresy':{'marker':{'min':1,'max':5}},
                'patient_id':{'wzorzec':'ZZ-[0-9]{2}','min':10,'max':20}}
    (tmp_path/'scenariusz.json').write_text(json.dumps(metadata))
    definitions = dictionary(tmp_path)
    spec = definitions.set_index('zmienna').loc['marker']
    assert float(spec['zakres_min']) == 1 and float(spec['zakres_max']) == 5
    assert id_constraints(definitions,metadata) == {'pattern':'ZZ-[0-9]{2}','min':10,'max':20}
