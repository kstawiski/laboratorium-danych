"""Spójność małego pakietu B; bez modelu i bez pandas."""
from pathlib import Path
import csv
import json
import re

ROOT = Path(__file__).resolve().parent/'fixtures'


def rows(name, delimiter=','):
    with (ROOT/name).open(encoding='utf-8-sig',newline='') as handle:
        return list(csv.DictReader(handle,delimiter=delimiter))


def test_every_fixture_difference_has_key_entry():
    clean = rows('rejestr_czysty.csv')
    dirty = rows('rejestr_brudny.csv',';')
    key = rows('klucz_bledow.csv')
    assert len(clean) == len(dirty) == 12 and len(key) == 16
    differences = {(i+2,column) for i,(truth,raw) in enumerate(zip(clean,dirty)) for column in truth if truth[column] != raw[column]}
    keyed = {(int(item['wiersz_excel']),item['zmienna']) for item in key}
    assert differences == keyed
    for item in key:
        index, variable = int(item['wiersz_excel'])-2,item['zmienna']
        assert item['wartosc_prawdziwa'] == clean[index][variable]
        assert item['wartosc_w_pliku'] == dirty[index][variable]
        assert item['patient_id_w_pliku'] == dirty[index]['patient_id']


def test_fixture_document_contract_and_pesel():
    schema = json.loads((ROOT/'ekstrakcja_schemat.json').read_text())
    gold = rows('ekstrakcja_klucz.csv')
    assert len(schema['properties']) == 25 and len(gold) == 2
    for item in gold:
        text = (ROOT/'dokumenty'/item['dokument']).read_text()
        assert 150 <= len(text.split()) <= 400
        assert item['patient_id'] in text
        for pesel in re.findall(r'\b\d{11}\b',text):
            checksum = (10 - sum(int(n)*w for n,w in zip(pesel[:10],[1,3,7,9,1,3,7,9,1,3])) % 10) % 10
            assert int(pesel[-1]) != checksum
    assert '88,4 µmol/l' in (ROOT/'dokumenty'/'DOK-01.txt').read_text()
    assert float(gold[0]['creatinine_mg_dl']) == 1.0
    assert gold[1]['diabetes'] == '' and gold[1]['smoking'] == ''
