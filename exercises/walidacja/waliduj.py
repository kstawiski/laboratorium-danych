#!/usr/bin/env python3
"""Walidacja PROSTATA-RT według reguly.yaml. Raportuje podejrzenia, nie naprawia danych."""
from __future__ import annotations
import argparse
import math
import re
from datetime import date
from pathlib import Path
import pandas as pd
import yaml
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'dane'
HIDDEN_MISSING = {'brak', 'nd', 'b.d.', '-', '999', '-9', '999.0', '-9.0'}
REPORT_COLUMNS = ['wiersz_excel','patient_id','zmienna','wartosc','regula','typ','powaga','opis']


def value_text(value):
    if value is None or (not isinstance(value,str) and pd.isna(value)):
        return ''
    return format(float(value),'.12g') if isinstance(value,float) else str(value)


def is_missing(value):
    return value_text(value).strip().lower() in HIDDEN_MISSING | {''}


def numeric(value):
    text = value_text(value)
    if is_missing(text) or not re.fullmatch(r'[-+]?(?:\d+(?:[.,]\d+)?|[.,]\d+)',text):
        return None
    num = float(text.replace(',','.'))
    return num if math.isfinite(num) else None


def iso_date(value):
    text = value_text(value)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def read_registry(path):
    path = Path(path)
    if path.suffix.lower()=='.xlsx':
        return pd.read_excel(path,sheet_name='dane',dtype=object,keep_default_na=False,engine='openpyxl')
    with path.open(encoding='utf-8-sig') as handle:
        sep = ';' if ';' in handle.readline() else ','
    return pd.read_csv(path,sep=sep,dtype=str,keep_default_na=False,encoding='utf-8-sig')


def read_rules(path=None):
    path = Path(path or DATA / 'reguly.yaml')
    catalog = yaml.safe_load(path.read_text(encoding='utf-8'))
    rules = catalog['reguly']
    ids = [r['id'] for r in rules]
    if len(ids)!=len(set(ids)):
        raise ValueError('Powtarzający się identyfikator reguły.')
    for r in rules:
        if not {'id','opis','typ','zmienne'} <= set(r):
            raise ValueError('Niepełna definicja reguły.')
        if not any(k in r for k in ['wyrazenie','zakres','kontrola']):
            raise ValueError('Reguła nie określa sposobu kontroli.')
    return rules


def validate(frame, dictionary=None, enabled_rules=None, rules_path=None):
    """Katalog YAML steruje zakresem, parametrami i opisem kontroli. Bez odczytu klucza."""
    dictionary = dictionary if dictionary is not None else pd.read_csv(DATA/'slownik_danych.csv',keep_default_na=False)
    expected = list(dictionary.zmienna)
    if set(expected)!=set(frame.columns):
        raise ValueError('Kolumny rejestru nie odpowiadają słownikowi.')
    rules = read_rules(rules_path)
    catalog = {r['id']:r for r in rules}
    enabled = set(catalog) if enabled_rules is None else set(enabled_rules)
    if enabled-set(catalog):
        raise ValueError('Nieznane reguły: '+', '.join(sorted(enabled-set(catalog))))
    frame = frame.reset_index(drop=True)
    definitions = dictionary.set_index('zmienna').to_dict('index')
    findings = []
    def add(i,v,rid,extra=''):
        spec=catalog[rid]
        findings.append(dict(wiersz_excel=i+2,patient_id=value_text(frame.at[i,'patient_id']),zmienna=v,
                             wartosc=value_text(frame.at[i,v]),regula=rid,typ=spec['typ'],powaga=spec.get('powaga','ostrzezenie'),
                             opis=spec['opis']+(' '+extra if extra else '')))
    def vars_for(rule):
        return expected if rule['zmienne']==['*'] else rule['zmienne']
    for rule in rules:
        rid=rule['id']
        if rid not in enabled:
            continue
        control=rule.get('kontrola')
        if control=='unikalny_id':
            for i in frame.index[frame.patient_id.map(value_text).duplicated(keep=False)]:
                add(i,'patient_id',rid)
            continue
        if control=='duplikat_rekordu':
            comparable=frame[expected].drop(columns='patient_id').map(value_text)
            for i in frame.index[comparable.duplicated(keep='first')]:
                add(i,'patient_id',rid)
            continue
        if 'wyrazenie' in rule and control is None:
            # Wyrażenia pandas tylko z zaufanego, lokalnego katalogu protokołu.
            converted=frame.copy()
            for v,d in definitions.items():
                if d['typ'] in {'liczba','liczba_calkowita','logiczna'}:
                    converted[v]=frame[v].map(numeric)
            mask=converted.eval(rule['wyrazenie'],engine='python').fillna(False)
            for i in frame.index[mask.astype(bool)]:
                for v in vars_for(rule):
                    add(i,v,rid)
            continue
        for i,row in frame.iterrows():
            if control in {'format_id','prywatnosc','brak','kategoria','liczba_format','calkowita','data_iso','jednostka','ponizej_oznaczalnosci','autokonwersja','struktura'} or 'zakres' in rule:
                for v in vars_for(rule):
                    raw=value_text(row[v]); d=definitions[v]; num=numeric(raw)
                    bad=False; extra=''
                    if control=='format_id':
                        bad=re.fullmatch(rule['wzorzec'],raw) is None
                    elif control=='prywatnosc':
                        bad=bool(re.search(r'(?<!\d)\d{11}(?!\d)',raw))
                    elif control=='brak':
                        bad=is_missing(raw) and (v not in {'death_date','notes'} or raw!='')
                    elif control=='kategoria':
                        bad=not is_missing(raw) and d['typ'] in {'kategoria','logiczna'} and raw not in str(d['dozwolone_wartosci']).split('|')
                    elif control=='liczba_format':
                        bad=not is_missing(raw) and d['typ'] in {'liczba','liczba_calkowita'} and (num is None or ',' in raw)
                    elif control=='calkowita':
                        bad=num is not None and d['typ']=='liczba_calkowita' and not num.is_integer()
                    elif control=='data_iso':
                        bad=d['typ']=='data' and not is_missing(raw) and iso_date(raw) is None
                    elif control=='jednostka':
                        bad=bool(re.search(r'µmol/l|umol/l|mmol/l|nmol/l|\blb\b',raw)) or (v=='creatinine_mg_dl' and num is not None and num>15)
                        extra='Jednostka jawna lub podejrzana; nie przeliczać wyłącznie na podstawie wartości.'
                    elif control=='ponizej_oznaczalnosci':
                        bad=raw.startswith('<')
                    elif control=='autokonwersja':
                        bad=bool(re.search(r'kwi|Apr',raw,re.I))
                    elif control=='struktura':
                        bad=(v=='rt_dose_gy' and '/' in raw) or (v=='notes' and bool(re.search(r'\bNT\s*;.*\bDM2\s*;',raw)))
                    elif 'zakres' in rule:
                        limits=rule['zakres']
                        lo=float(d['zakres_min']) if limits=='slownik' and d['typ'] in {'liczba','liczba_calkowita'} else None
                        hi=float(d['zakres_max']) if lo is not None else None
                        if isinstance(limits,dict):
                            lo,hi=limits['min'],limits['max']
                        bad=num is not None and lo is not None and not lo<=num<=hi
                    if bad:
                        add(i,v,rid,extra)
                continue
            birth,dx,start,last,dead=[iso_date(row[v]) for v in ['birth_date','diagnosis_date','rt_start_date','psa_last_date','death_date']]
            if control=='wiek' and birth and start:
                age=start.year-birth.year-((start.month,start.day)<(birth.month,birth.day))
                if not rule['min']<=age<=rule['max']:
                    add(i,'birth_date',rid,f'Wyliczony wiek: {age} lat.')
            elif control=='daty':
                for a,b in rule['kolejnosc']:
                    da,db=iso_date(row[a]),iso_date(row[b])
                    if da and db and (da>db or (a=='rt_start_date' and b=='psa_last_date' and da==db)):
                        target=a if a in {'diagnosis_date','psa_last_date'} else b
                        add(i,target,rid,f'{a} ma poprzedzać {b}.')
            elif control in {'gleason','isup','ryzyko'}:
                p,s,score,grade,psa=[numeric(row[v]) for v in ['gleason_primary','gleason_secondary','gleason_score','isup_grade','psa_dx_ng_ml']]
                pair_ok=p in {3,4,5} and s in {3,4,5}
                expected_grade={(3,3):1,(3,4):2,(4,3):3}.get((p,s),4 if pair_ok and p+s==8 else 5)
                if control=='gleason' and pair_ok and score is not None and score!=p+s:
                    add(i,'gleason_score',rid)
                if control=='isup' and pair_ok and grade in {1,2,3,4,5} and grade!=expected_grade:
                    add(i,'isup_grade',rid)
                if control=='ryzyko' and psa is not None and 0<=psa<=500 and grade in {1,2,3,4,5} and row.ct_stage in rule['ct_dozwolone'] and row.cn_stage in {'N0','N1'}:
                    group='wysokie' if psa>20 or grade>=4 or row.ct_stage in rule['ct_wysokie'] or row.cn_stage=='N1' else 'niskie' if psa<10 and grade==1 and row.ct_stage in {'T1c','T2a'} else 'posrednie'
                    if row.risk_group in {'niskie','posrednie','wysokie'} and row.risk_group!=group:
                        add(i,'risk_group',rid,f'Z wpisanych pól wynika {group}.')
            elif control=='schemat_rt':
                dose,fr=numeric(row.rt_dose_gy),numeric(row.rt_fractions)
                if dose is not None and fr is not None and [dose,fr] not in rule['schematy']:
                    add(i,'rt_dose_gy',rid)
                    add(i,'rt_fractions',rid)
            elif control=='sbrt':
                fr=numeric(row.rt_fractions)
                if fr is not None and row.rt_technique in {'IMRT','VMAT','SBRT'} and (row.rt_technique=='SBRT')!=(fr==5):
                    add(i,'rt_technique',rid);add(i,'rt_fractions',rid)
            elif control=='adt':
                adt,months=numeric(row.adt),numeric(row.adt_months)
                if adt in {0,1} and months is not None and ((adt==0 and months!=0) or (adt==1 and months==0)):
                    add(i,'adt',rid);add(i,'adt_months',rid)
                elif adt==1 and months is not None and ((row.risk_group=='wysokie' and not rule['wysokie_min']<=months<=rule['wysokie_max']) or (row.risk_group=='posrednie' and months!=rule['posrednie_typowo'])):
                    add(i,'adt_months',rid,'Odstępstwo od typowego czasu; wymaga uzasadnienia, nie automatycznej korekty.')
            elif control=='phoenix':
                nadir,psa,flag=[numeric(row[v]) for v in ['psa_nadir_ng_ml','psa_last_ng_ml','bcr_phoenix']]
                if nadir is not None and psa is not None and 0<=nadir<=500 and 0<=psa<=500 and flag in {0,1}:
                    expected_flag=int(psa>=nadir+rule['przyrost'])
                    if flag!=expected_flag:
                        add(i,'bcr_phoenix',rid)
            elif control=='nadir':
                nadir,psa=numeric(row.psa_nadir_ng_ml),numeric(row.psa_last_ng_ml)
                if nadir is not None and psa is not None and 0<=nadir<=500 and 0<=psa<=500 and nadir>psa:
                    add(i,'psa_nadir_ng_ml',rid);add(i,'psa_last_ng_ml',rid)
            elif control=='zgon':
                if (value_text(row.death)=='1' and is_missing(row.death_date)) or (value_text(row.death)=='0' and not is_missing(row.death_date)):
                    add(i,'death',rid);add(i,'death_date',rid)
            elif control not in {'wiek','daty','gleason','isup','ryzyko','schemat_rt','sbrt','adt','phoenix','nadir','zgon'}:
                raise ValueError('Nieznana kontrola w YAML: '+str(control))
    return pd.DataFrame(findings,columns=REPORT_COLUMNS).drop_duplicates().reset_index(drop=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plik',nargs='?',type=Path,default=DATA/'rejestr_brudny.xlsx')
    parser.add_argument('--slownik',type=Path,default=DATA/'slownik_danych.csv')
    parser.add_argument('--reguly',type=Path,default=DATA/'reguly.yaml')
    parser.add_argument('--raport',type=Path,default=DATA/'wyniki_referencyjne/walidacja_reguly_raport.csv')
    args=parser.parse_args()
    if not args.raport.resolve().is_relative_to(ROOT):
        parser.error('Raport wolno zapisać tylko w exercises.')
    report=validate(read_registry(args.plik),pd.read_csv(args.slownik,keep_default_na=False),rules_path=args.reguly)
    args.raport.parent.mkdir(parents=True,exist_ok=True)
    report.to_csv(args.raport,index=False,encoding='utf-8',lineterminator='\n')
    print(f'Naruszenia reguł: {len(report)}; raport: {args.raport}')
if __name__=='__main__':
    main()
