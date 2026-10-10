"""Mały, samodzielny pakiet PROSTATA-RT. Nie czyta exercises/."""
from pathlib import Path
import json
import pandas as pd
from lab.data import dictionary, excel_bytes
from lab.rules import package_rules, run_rules

ROOT = Path(__file__).resolve().parent / 'fixtures'


def build():
    definitions = dictionary(ROOT)
    rows = []
    for i in range(12):
        row = dict(patient_id=f'PR-{i+1:03d}' if i < 10 else f'PR-{101+i-10:03d}', sex='M',
            birth_date='1955-04-03', diagnosis_date='2020-12-01', rt_start_date='2021-04-03',
            weight_kg=78, psa_dx_ng_ml=12, gleason_primary=3, gleason_secondary=4, gleason_score=7,
            isup_grade=2, ct_stage='T2b', cn_stage='N0', risk_group='posrednie', rt_technique='VMAT',
            rt_dose_gy=60, rt_fractions=20, adt=1, adt_months=6, testosterone_ng_dl=20,
            psa_nadir_ng_ml=0.2, psa_last_ng_ml=0.3, psa_last_date='2025-04-03', bcr_phoenix=0,
            gu_toxicity_max=1, gi_toxicity_max=0, creatinine_mg_dl=1, hemoglobin_g_dl=13.5,
            diabetes=0, hypertension=1, smoking='former', death=0, death_date='', notes='')
        row['weight_kg'] += i
        if i == 7:  # Rzadkie, dozwolone wartości; żadnego alarmu reguł.
            row.update(birth_date='1932-04-03', rt_technique='SBRT', rt_dose_gy=36.25,
                       rt_fractions=5, psa_dx_ng_ml=148, cn_stage='N1', risk_group='wysokie',
                       adt_months=24, gu_toxicity_max=3, testosterone_ng_dl=180,
                       notes='Pierwszy miesiąc ADT; testosteron przed pełnym efektem leczenia.')
        rows.append(row)
    clean = pd.DataFrame(rows, columns=definitions.zmienna)
    dirty = clean.copy().astype(object)
    changes = [(0,'rt_dose_gy',780),(1,'psa_dx_ng_ml',-1),(2,'creatinine_mg_dl','88,4'),
               (3,'gleason_score',8),(3,'isup_grade',3),(4,'psa_last_date','2020-01-01'),
               (4,'death',1),(5,'hemoglobin_g_dl',-9),(5,'psa_last_ng_ml',999),
               (6,'patient_id','pr 007'),(6,'sex','male'),(8,'adt',0),
               (8,'weight_kg','nd'),(9,'notes','Fikcyjny PESEL 55040312340; NT; DM2; metformina'),
               (10,'risk_group','niskie'),(11,'psa_last_ng_ml',3.3)]
    for index, variable, value in changes: dirty.at[index,variable] = value
    key = pd.DataFrame([dict(error_id=f'F-{j:02d}', patient_id_w_pliku=dirty.at[i,'patient_id'],
        wiersz_excel=i+2, zmienna=v, wartosc_w_pliku=dirty.at[i,v], wartosc_prawdziwa=clean.at[i,v],
        kategoria='format', jak_wykryc='Słownik i protokół', decyzja='zapytanie_do_osrodka',
        uzasadnienie='Celowa zmiana w syntetycznym zestawie próbnym.', wykrywalne_regula=1, trudnosc='latwy')
        for j,(i,v,_) in enumerate(changes,1)])
    traps = pd.DataFrame([dict(patient_id='PR-008',zmienna=v,wartosc=clean.at[7,v],
        uzasadnienie='Wartość rzadka, dopuszczona przez protokół.')
        for v in ['rt_dose_gy','birth_date','psa_dx_ng_ml','gu_toxicity_max','testosterone_ng_dl']])
    for name, frame, sep in [('rejestr_czysty.csv',clean,','),('rejestr_brudny.csv',dirty,';'),
                             ('klucz_bledow.csv',key,','),('pulapki_nie_bledy.csv',traps,',')]:
        frame.to_csv(ROOT/name,index=False,sep=sep,encoding='utf-8-sig')
    for name, frame in [('rejestr_brudny.xlsx',dirty),('klucz_bledow.xlsx',key),('slownik_danych.xlsx',definitions)]:
        (ROOT/name).write_bytes(excel_bytes(frame))
    schema = json.loads((ROOT/'ekstrakcja_schemat.json').read_text())
    gold = []
    for i in range(2):
        row = clean.iloc[10+i]
        values = {f:row[f] for f in schema['properties']}
        if i == 1: values.update(diabetes=None, smoking=None)
        name = f'DOK-{i+1:02d}.txt'
        gold.append(dict(dokument=name,**values))
        text = f'''SYNTHETYCZNA KARTA INFORMACYJNA Z LECZENIA RADIOTERAPIĄ
Pacjent: Fikcyjny Jan Próbny. Kod: {row.patient_id}. Fikcyjny PESEL: 55040312340.
Data urodzenia 03.04.1955. Rozpoznanie: ca prostatae, PSA 12 ng/ml,
Gs 3+4=7, ISUP 2, cT2b cN0. Uproszczona grupa ryzyka: pośrednia.
Pierwsza frakcja RT 03.04.2021. VMAT 60 Gy w 20 frakcjach na prostatę.
ADT zaplanowano łącznie na 6 miesięcy. Nie opisano zmian przerzutowych.
Ostatnie PSA 0,3 ng/ml, nadir PSA po radioterapii 0,2 ng/ml; bez nawrotu
biochemicznego według definicji Phoenix. Maksymalna toksyczność GU CTCAE G1,
GI CTCAE G0 w całym okresie obserwacji. Kreatynina 88,4 µmol/l; hemoglobina
13,5 g/dl. Nadciśnienie rozpoznane przed leczeniem. '''
        text += 'Nie stwierdzono cukrzycy. Nie pali od 10 lat. ' if i == 0 else 'Brak wywiadu dotyczącego cukrzycy i palenia. '
        text += '''Wizyta kontrolna odbyła się w kwietniu. Pacjent zgłasza dobry stan
ogólny i przyjmuje zalecone leczenie. Bez dolegliwości ze strony przewodu
pokarmowego na aktualnej wizycie. Omówiono dalszą obserwację PSA i postępowanie
w razie nowych dolegliwości. Dokument służy wyłącznie ćwiczeniom. Każda wartość,
identyfikator i informacja o leczeniu zostały wymyślone. Zapis aktualnego stanu
nie zastępuje oceny maksymalnej toksyczności całego okresu leczenia. Wyniki należy
przepisywać z podanych źródeł. Informacji nieobecnych w dokumencie nie wolno
uzupełniać na podstawie typowego postępowania ani samego rozpoznania choroby.'''
        (ROOT/'dokumenty'/name).write_text(text,encoding='utf-8')
    pd.DataFrame(gold).to_csv(ROOT/'ekstrakcja_klucz.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame([dict(dokument='DOK-01.txt',zmienna='creatinine_mg_dl',dlaczego_trudne='jednostka')]).to_csv(ROOT/'ekstrakcja_trudnosci.csv',index=False)
    rules, messages = package_rules(ROOT,definitions)
    assert not messages, messages
    (ROOT/'wyniki_referencyjne').mkdir(exist_ok=True)
    run_rules(dirty,definitions,rules).to_csv(ROOT/'wyniki_referencyjne'/'walidacja_reguly_raport.csv',index=False)
    (ROOT/'README_dane.md').write_text('Mały syntetyczny zestaw PROSTATA-RT: 12 rekordów, 16 zmian, 2 dokumenty. Odtworzenie: python -m tests.build_fixture. Metadane są zapisane lokalnie; pakiet exercises nie jest potrzebny.\n',encoding='utf-8')

if __name__ == '__main__': build()
