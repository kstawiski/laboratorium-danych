#!/usr/bin/env python3
"""Deterministyczny, w pełni fikcyjny pakiet PROSTATA-RT. Bez danych wejściowych."""
from __future__ import annotations
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dane"
SEED = 20261011
LAYOUT_SEED = SEED + 2
# Numery przykładów klinicznych przed losowaniem, nie pozycje w pliku.
ERROR_CASES = (0, 1, 2, 4, *range(6, 57))
TRAP_CASES = tuple(range(90, 95))
COLUMNS = "patient_id sex birth_date diagnosis_date rt_start_date weight_kg psa_dx_ng_ml gleason_primary gleason_secondary gleason_score isup_grade ct_stage cn_stage risk_group rt_technique rt_dose_gy rt_fractions adt adt_months testosterone_ng_dl psa_nadir_ng_ml psa_last_ng_ml psa_last_date bcr_phoenix gu_toxicity_max gi_toxicity_max creatinine_mg_dl hemoglobin_g_dl diabetes hypertension smoking death death_date notes".split()
EXTRACT = "patient_id birth_date rt_start_date psa_dx_ng_ml gleason_primary gleason_secondary isup_grade ct_stage cn_stage risk_group rt_technique rt_dose_gy rt_fractions adt adt_months psa_nadir_ng_ml psa_last_ng_ml bcr_phoenix gu_toxicity_max gi_toxicity_max creatinine_mg_dl hemoglobin_g_dl diabetes hypertension smoking".split()
KEY_COLUMNS = "error_id patient_id_w_pliku wiersz_excel zmienna wartosc_w_pliku wartosc_prawdziwa kategoria jak_wykryc decyzja uzasadnienie wykrywalne_regula trudnosc".split()
CATEGORIES = "identyfikator kodowanie format_daty logika_czasowa jednostka liczba_jako_tekst brak_danych zakres spojnosc_pol duplikat kategoria struktura prywatnosc".split()
PROTOCOL = {
    "gleason": "gleason_score = gleason_primary + gleason_secondary.",
    "isup": "3+3: 1; 3+4: 2; 4+3: 3; suma 8: 4; suma 9–10: 5.",
    "ryzyko": "Najpierw wysokie: PSA >20 lub ISUP 4–5 lub cT2c–cT4 lub cN1. Następnie niskie: PSA <10, ISUP 1, cT1c–cT2a i cN0. Pozostałe: posrednie. Definicja uproszczona do ćwiczenia; M1 poza rejestrem.",
    "phoenix": "bcr_phoenix = 1, gdy PSA ostatnie >= nadir + 2 ng/ml; inaczej 0. Bez obu pomiarów: null.",
    "rt": "78/39, 76/38, 60/20, 62/20, 70/28, 36,25/5 i 40/5 (Gy/fr.). SBRT wtedy i tylko wtedy, gdy 5 frakcji.",
    "adt": "adt=0 wymaga adt_months=0. ADT 6 mies. typowo w ryzyku pośrednim niekorzystnym; 18–36 mies. w wysokim. adt_months: całkowity zaplanowany czas ADT.",
    "jednostki": "Kreatynina µmol/l ÷ 88,4 = mg/dl; hemoglobina mmol/l ÷ 0,6206 = g/dl; testosteron nmol/l × 28,84 = ng/dl; masa lb × 0,45359237 = kg.",
    "ekstrakcja": "Daty z ukośnikiem w dokumentach: DD/MM/RRRR. Brak lub nierozstrzygnięta sprzeczność: null. Wyniku poniżej oznaczalności nie zamieniać na zero. Potwierdzony aneks histopatologiczny rozstrzyga sprzeczne ISUP; bez aneksu ISUP=null. Stopień CTCAE dotyczy maksymalnej toksyczności w całej obserwacji, nie tylko bieżącej wizyty."
}

def text_value(value):
    """Jedna reprezentacja wartości do porównania CSV, XLSX i klucza."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ""
    if isinstance(value, (float, np.floating)):
        return format(float(value), ".12g")
    return str(value)


def csv_write(frame, path, *, dirty=False):
    frame.map(text_value).to_csv(path, index=False, sep=";" if dirty else ",",
                              encoding="utf-8-sig" if dirty else "utf-8", lineterminator="\n")


# Słownik czyta się w Excelu: szerokie kolumny z regułą i uwagami, tekst zawijany.
DICTIONARY_WIDTHS = {"zmienna": 22, "etykieta": 28, "typ": 14, "jednostka": 11, "dozwolone_wartosci": 24,
                     "zakres_min": 10, "zakres_max": 10, "kod_braku": 24, "regula_walidacyjna": 60, "uwagi": 44}


def xlsx_write(frame, path, sheet="dane", widths=None):
    wb = Workbook()
    wb.properties.creator = "Generator syntetyczny PROSTATA-RT"
    wb.properties.created = wb.properties.modified = datetime(2026, 10, 10, 0, 0, 0)
    ws = wb.active
    ws.title = sheet
    ws.append(list(frame.columns))
    for row in frame.itertuples(index=False, name=None):
        ws.append([None if text_value(v) == "" else v.item() if isinstance(v, np.generic) else v
                   for v in row])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="315A75")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col in ws.columns:
        name = str(col[0].value)
        ws.column_dimensions[col[0].column_letter].width = widths[name] if widths and name in widths else min(52, max(16, len(name) + 2))
        if widths:
            for cell in col[1:]:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    buffer = io.BytesIO()
    wb.save(buffer)
    # Stałe znaczniki czasu kontenera ZIP: identyczny XLSX również na poziomie bajtów.
    with zipfile.ZipFile(buffer) as z:
        contents = [(n, z.read(n)) for n in z.namelist()]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, content in contents:
            if name == "docProps/core.xml":
                # openpyxl nadpisuje modified podczas save(), niezależnie od właściwości wb.
                content = re.sub(rb'(<dcterms:modified\b[^>]*>).*?(</dcterms:modified>)',
                                 rb'\g<1>2026-10-10T00:00:00Z\g<2>', content)
            info = zipfile.ZipInfo(name, (2026, 10, 10, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            z.writestr(info, content)
    path.write_bytes(output.getvalue())


def invalid_pesel(birth, sex, serial):
    d = date.fromisoformat(birth)
    month = d.month + {1800: 80, 1900: 0, 2000: 20, 2100: 40, 2200: 60}[d.year // 100 * 100]
    # Dziesiąta cyfra zachowuje umowne kodowanie płci; kontrolna jest zawsze zła.
    first = f"{d.year % 100:02d}{month:02d}{d.day:02d}{serial % 1000:03d}{1 if sex == 'M' else 2}"
    checksum = (-sum(int(a) * b for a, b in zip(first, [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]))) % 10
    return first + str((checksum + 1) % 10)


def isup(primary, secondary):
    total = primary + secondary
    return {(3, 3): 1, (3, 4): 2, (4, 3): 3}.get((primary, secondary), 4 if total == 8 else 5)


def risk(psa, grade, ct, cn):
    if psa > 20 or grade >= 4 or ct in {'T2c', 'T3a', 'T3b', 'T4'} or cn == 'N1':
        return 'wysokie'
    return 'niskie' if psa < 10 and grade == 1 and ct in {'T1c', 'T2a'} else 'posrednie'


def make_layout():
    """Losuj pozycje przykładów z zachowaniem limitów w sześciu blokach."""
    rng = np.random.default_rng(LAYOUT_SEED)
    # Zachowaj literalny wariant „pr 014”, źródło dodatkowego duplikatu
    # oraz histopatologię dwóch dokumentów ze sprzecznym ISUP.
    fixed = {13, 75, 115, 116}
    movable = np.array([i for i in range(120) if i not in fixed])
    for _ in range(10000):
        layout = np.arange(120)
        layout[movable] = rng.permutation(movable)
        counts = np.bincount(layout[list(ERROR_CASES)] // 20, minlength=6)
        if np.all((counts >= 7) & (counts <= 12)) and len(set(layout[list(TRAP_CASES)] // 20)) == 5:
            return layout
    raise RuntimeError('Nie znaleziono rozmieszczenia zgodnego z limitami.')


def make_clean(layout=None):
    layout = make_layout() if layout is None else layout
    rng = np.random.default_rng(SEED)
    birth_rng = np.random.default_rng(SEED + 1)
    recurrences = {47, 60, 64, 68, 72, 76, 80, 84, 88, 92, 100, 104, 108, 112, 116}
    deaths = {24, 49, 80, 110, 118}
    pairs = [(3, 3), (3, 4), (4, 3), (4, 4), (4, 5), (5, 4), (5, 5)]
    schedules = [(78, 39), (76, 38), (60, 20), (62, 20), (70, 28)]
    rows = []
    for i in range(120):
        start = date(2021, 1, 4) + timedelta(days=int(rng.integers(0, 720)))
        age = int(rng.integers(55, 86))
        month, day = int(birth_rng.integers(1, 13)), int(birth_rng.integers(1, 29))
        birthday = date(start.year - age - int((start.month, start.day) < (month, day)), month, day)
        dx = start - timedelta(days=int(rng.integers(60, 181)))
        p, s = pairs[int(rng.choice(len(pairs), p=[.20, .27, .20, .16, .09, .06, .02]))]
        grade = isup(p, s)
        psa = round(float(np.clip(rng.lognormal(2.45, .65), 2.2, 95)), 2)
        ct = str(rng.choice(['T1c', 'T2a', 'T2b', 'T2c', 'T3a', 'T3b', 'T4'], p=[.25, .18, .18, .12, .18, .07, .02]))
        cn = 'N1' if rng.random() < .10 else 'N0'
        group = risk(psa, grade, ct, cn)
        sbrt = group != 'wysokie' and rng.random() < .25
        tech = 'SBRT' if sbrt else str(rng.choice(['IMRT', 'VMAT'], p=[.20, .80]))
        dose, fractions = (float(rng.choice([36.25, 40])), 5) if sbrt else schedules[int(rng.integers(0, 5))]
        adt = int(group == 'wysokie' or (group == 'posrednie' and rng.random() < .65))
        months = int(rng.choice([18, 24, 36])) if group == 'wysokie' else 6 if adt else 0
        nadir = round(float(rng.uniform(.02, .45) if adt else rng.uniform(.18, .8)), 2)
        last = round(nadir + float(rng.uniform(2.05, 6.0) if i in recurrences else rng.uniform(0, 1.1)), 2)
        last_date = start + timedelta(days=int(rng.integers(1000, 1201)))
        dm, nt = int(rng.random() < .23), int(rng.random() < .61)
        rows.append(dict(zip(COLUMNS, [
            f'PR-{i+1:03d}', 'M', birthday.isoformat(), dx.isoformat(), start.isoformat(),
            round(float(np.clip(rng.normal(82, 13), 52, 121)), 1), psa, p, s, p+s, grade,
            ct, cn, group, tech, dose, fractions, adt, months,
            round(float(rng.uniform(7, 35) if adt else rng.uniform(230, 610)), 1),
            nadir, last, last_date.isoformat(), int(i in recurrences),
            int(rng.choice([0, 1, 2], p=[.28, .53, .19])), int(rng.choice([0, 1, 2], p=[.57, .36, .07])),
            round(float(np.clip(rng.normal(1.02, .2), .6, 1.65)), 2), round(float(rng.uniform(12.0, 15.8)), 2),
            dm, nt, str(rng.choice(['never', 'former', 'current'], p=[.40, .45, .15])),
            int(i in deaths), (last_date + timedelta(days=80)).isoformat() if i in deaths else '',
            'Dane syntetyczne. Testosteron oznaczony w trakcie ADT.' if adt else 'Dane syntetyczne. Testosteron przed leczeniem; bez ADT.'
        ])))
    frame = pd.DataFrame(rows, columns=COLUMNS)
    overrides = {
        17: {'psa_nadir_ng_ml': .005},
        18: {'birth_date': '1960-04-03', 'diagnosis_date': '2025-04-03', 'rt_start_date': '2025-06-03', 'psa_last_date': '2026-06-03'},
        19: {'birth_date': '1955-03-04', 'diagnosis_date': '2024-12-03', 'rt_start_date': '2025-03-04', 'psa_last_date': '2026-06-03'},
        20: {'psa_last_date': '2025-04-03'},
        21: {'birth_date': '1965-04-03', 'diagnosis_date': '2025-04-03', 'rt_start_date': '2025-06-03', 'psa_last_date': '2026-06-03'},
        22: {'psa_last_date': '2025-04-03'},
        26: {'creatinine_mg_dl': 1.0}, 27: {'creatinine_mg_dl': 1.2}, 28: {'creatinine_mg_dl': .8},
        29: {'hemoglobin_g_dl': round(8.4 / .6206, 2)}, 30: {'hemoglobin_g_dl': round(8.8 / .6206, 2)},
        31: {'testosterone_ng_dl': 17.3, 'adt': 1}, 32: {'weight_kg': 82.0},
        33: {'psa_dx_ng_ml': 12.4}, 34: {'psa_nadir_ng_ml': .1, 'psa_last_ng_ml': .2},
        35: {'rt_technique': 'VMAT', 'rt_dose_gy': 78, 'rt_fractions': 39},
        36: {'gleason_primary': 3, 'gleason_secondary': 4},
        37: {'rt_technique': 'VMAT', 'rt_dose_gy': 60, 'rt_fractions': 20},
        42: {'gleason_primary': 4, 'gleason_secondary': 3},
        43: {'gleason_primary': 4, 'gleason_secondary': 3},
        44: {'psa_dx_ng_ml': 25.0},
        45: {'rt_technique': 'VMAT', 'rt_dose_gy': 78, 'rt_fractions': 39},
        46: {'gleason_primary': 4, 'gleason_secondary': 3, 'psa_dx_ng_ml': 12.0, 'ct_stage': 'T2b', 'cn_stage': 'N0', 'adt': 1},
        50: {'rt_technique': 'VMAT', 'rt_dose_gy': 78, 'rt_fractions': 39},
        51: {'ct_stage': 'T2b'}, 52: {'rt_technique': 'IMRT', 'rt_dose_gy': 76, 'rt_fractions': 38},
        56: {'diabetes': 1, 'hypertension': 1, 'notes': 'Nadciśnienie tętnicze. Cukrzyca typu 2. Metformina 1000 mg dwa razy dziennie; ASA.'},
        90: {'psa_dx_ng_ml': 6.3, 'gleason_primary': 3, 'gleason_secondary': 3, 'ct_stage': 'T1c', 'cn_stage': 'N0', 'rt_technique': 'SBRT', 'rt_dose_gy': 36.25, 'rt_fractions': 5, 'adt': 0},
        91: {'birth_date': '1932-04-03', 'rt_start_date': '2021-04-03', 'diagnosis_date': '2021-01-05'},
        92: {'psa_dx_ng_ml': 148.0, 'cn_stage': 'N1', 'rt_technique': 'VMAT', 'rt_dose_gy': 78, 'rt_fractions': 39, 'adt': 1},
        93: {'gu_toxicity_max': 3, 'notes': 'Maksymalna toksyczność GU CTCAE G3: zatrzymanie moczu wymagające cewnikowania podczas RT; obecnie bez cewnika.'},
        94: {'testosterone_ng_dl': 180.0, 'adt': 1, 'notes': 'Testosteron 180 ng/dl pobrano w pierwszym miesiącu ADT, 12 dni po pierwszym podaniu agonisty LHRH; wczesny pomiar nie świadczy o nieskuteczności całego leczenia.'},
        115: {'gleason_primary': 4, 'gleason_secondary': 3},
        116: {'gleason_primary': 4, 'gleason_secondary': 3},
    }
    for i, changes in overrides.items():
        for col, val in changes.items():
            frame.at[i, col] = val
    for i, r in frame.iterrows():
        grade = isup(r.gleason_primary, r.gleason_secondary)
        group = risk(r.psa_dx_ng_ml, grade, r.ct_stage, r.cn_stage)
        frame.at[i, 'gleason_score'] = r.gleason_primary + r.gleason_secondary
        frame.at[i, 'isup_grade'] = grade
        frame.at[i, 'risk_group'] = group
        if group == 'wysokie':
            frame.at[i, 'adt'] = 1
            if r.rt_technique == 'SBRT':
                frame.at[i, 'rt_technique'], frame.at[i, 'rt_dose_gy'], frame.at[i, 'rt_fractions'] = 'VMAT', 78, 39
        months = 24 if group == 'wysokie' else 6 if frame.at[i, 'adt'] else 0
        frame.at[i, 'adt_months'] = months
        if group == 'niskie':
            frame.at[i, 'adt'], frame.at[i, 'adt_months'] = 0, 0
        if i not in {31, 94}:
            frame.at[i, 'testosterone_ng_dl'] = round(float(rng.uniform(7, 35) if frame.at[i, 'adt'] else rng.uniform(230, 610)), 1)
        if i not in {56, 93, 94}:
            frame.at[i, 'notes'] = ('Dane syntetyczne. Testosteron oznaczony w trzecim miesiącu ADT.' if frame.at[i, 'adt'] else 'Dane syntetyczne. Testosteron przed leczeniem; bez ADT.')
    # Przenieś całe przykłady razem z prawdą; identyfikatory i kolejność
    # PR-001..PR-120 pozostają związane z pozycją w rejestrze.
    frame = frame.iloc[np.argsort(layout)].reset_index(drop=True)
    frame['patient_id'] = [f'PR-{i+1:03d}' for i in range(120)]
    # Dla dokumentów z Hb w mmol/l zachowujemy typową dokładność 0,1 mmol/l.
    # Prawda w g/dl jest jawnym przeliczeniem tego pomiaru, nie dodatkową precyzją.
    for j in range(20):
        if j % 4 in {1, 2}:
            measured = round(frame.at[100 + j, 'hemoglobin_g_dl'] * .6206, 1)
            frame.at[100 + j, 'hemoglobin_g_dl'] = round(measured / .6206, 2)
    frame['bcr_phoenix'] = (frame.psa_last_ng_ml >= frame.psa_nadir_ng_ml + 2).astype(int)
    return frame


def make_dictionary():
    labels = [
        'Kod pacjenta', 'Płeć', 'Data urodzenia', 'Data rozpoznania', 'Pierwsza frakcja RT', 'Masa ciała',
        'PSA przy rozpoznaniu', 'Dominujący wzorzec Gleasona', 'Drugorzędny wzorzec Gleasona', 'Suma Gleasona', 'Grupa stopnia ISUP',
        'Kliniczne T', 'Kliniczne N', 'Grupa ryzyka wg protokołu', 'Technika RT', 'Dawka na prostatę', 'Liczba frakcji na prostatę',
        'Stosowanie ADT', 'Zaplanowany czas ADT', 'Testosteron', 'Nadir PSA po RT', 'Ostatnie PSA', 'Data ostatniego PSA',
        'Nawrót wg Phoenix', 'Maksymalna toksyczność GU', 'Maksymalna toksyczność GI', 'Kreatynina', 'Hemoglobina',
        'Cukrzyca', 'Nadciśnienie tętnicze', 'Palenie', 'Zgon', 'Data zgonu', 'Uwagi'
    ]
    categories = {'sex': 'M', 'ct_stage': 'T1c|T2a|T2b|T2c|T3a|T3b|T4', 'cn_stage': 'N0|N1',
                  'risk_group': 'niskie|posrednie|wysokie', 'rt_technique': 'IMRT|VMAT|SBRT', 'smoking': 'never|former|current'}
    ranges = {'weight_kg': (35, 220, 'kg'), 'psa_dx_ng_ml': (0, 500, 'ng/ml'),
              'gleason_primary': (3, 5, ''), 'gleason_secondary': (3, 5, ''), 'gleason_score': (6, 10, ''),
              'isup_grade': (1, 5, ''), 'rt_dose_gy': (1, 100, 'Gy'), 'rt_fractions': (1, 45, 'fr.'),
              'adt_months': (0, 36, 'mies.'), 'testosterone_ng_dl': (0, 1200, 'ng/dl'),
              'psa_nadir_ng_ml': (0, 500, 'ng/ml'), 'psa_last_ng_ml': (0, 500, 'ng/ml'),
              'gu_toxicity_max': (0, 5, 'CTCAE'), 'gi_toxicity_max': (0, 5, 'CTCAE'),
              'creatinine_mg_dl': (.2, 15, 'mg/dl'), 'hemoglobin_g_dl': (5, 20, 'g/dl')}
    integers = {'gleason_primary', 'gleason_secondary', 'gleason_score', 'isup_grade', 'rt_fractions', 'adt_months', 'gu_toxicity_max', 'gi_toxicity_max'}
    binary = {'adt', 'bcr_phoenix', 'diabetes', 'hypertension', 'death'}
    details = {
        'patient_id': ('PR-001..PR-120; unikalny, bez identyfikatora osobowego.', 'Dodatkowy duplikat pod PR-121 jest błędem struktury kohorty.'),
        'birth_date': ('Pełna data ISO; wiek w dniu RT 18–105 lat.', 'Typowa kohorta 55–85 lat; 89 lat jest dozwolone.'),
        'diagnosis_date': ('Data ISO nie późniejsza niż rozpoczęcie RT.', 'Rozpoznanie przed leczeniem radykalnym.'),
        'rt_start_date': ('Data pierwszej frakcji w ISO.', 'Nie mylić z datą kwalifikacji ani rozpoczęcia ADT.'),
        'gleason_score': (PROTOCOL['gleason'], 'Autokonwersja 3-4 w datę nie jest wynikiem histopatologicznym.'),
        'isup_grade': (PROTOCOL['isup'], 'Rozbieżność między opisem wzorców a ISUP wymaga weryfikacji preparatów lub aneksu.'),
        'risk_group': (PROTOCOL['ryzyko'], 'Uproszczenie dydaktyczne; nie pełny algorytm EAU.'),
        'rt_dose_gy': (PROTOCOL['rt'], 'Dawka całkowita na prostatę, nie dawka na węzły. 36,25/5 jest poprawne.'),
        'rt_fractions': (PROTOCOL['rt'], 'Pole nie obejmuje osobnej liczby frakcji obszaru węzłowego.'),
        'rt_technique': ('IMRT, VMAT lub SBRT; SBRT ⇔ 5 frakcji.', 'Nie normalizować nieznanej techniki bez źródła.'),
        'adt': (PROTOCOL['adt'], '0 oznacza udokumentowane niestosowanie; brak wzmianki to null.'),
        'adt_months': (PROTOCOL['adt'], 'Czas zaplanowany, nie czas od pierwszego podania do pobrania krwi.'),
        'testosterone_ng_dl': ('0–1200 ng/dl; nmol/l × 28,84.', '180 ng/dl w pierwszym miesiącu ADT to dopuszczalna pułapka. Sama liczba nie identyfikuje jednostki.'),
        'psa_nadir_ng_ml': ('Nadir ≤ ostatnie PSA; <0,01 wymaga jawnego sposobu kodowania wyników cenzorowanych.', 'Nie podstawiać zera ani połowy granicy oznaczalności.'),
        'psa_last_date': ('ISO; po rozpoczęciu RT i przed datą zgonu.', 'Phoenix nie rozstrzyga etiologii wzrostu PSA.'),
        'bcr_phoenix': (PROTOCOL['phoenix'], 'Definicja protokołu ćwiczeniowego.'),
        'creatinine_mg_dl': ('0,2–15 mg/dl; µmol/l ÷ 88,4.', 'Inną jednostkę potwierdzić, jeśli nie zapisano jej w komórce lub dokumencie.'),
        'hemoglobin_g_dl': ('5–20 g/dl; mmol/l ÷ 0,6206.', '8,4 może być prawdziwą anemią albo inną jednostką; sama liczba nie rozstrzyga.'),
        'gu_toxicity_max': ('Całkowite 0–5 CTCAE; maksimum całej obserwacji.', 'Pojedyncze G3 jest prawdziwe i nie podlega usunięciu.'),
        'gi_toxicity_max': ('Całkowite 0–5 CTCAE; maksimum całej obserwacji.', 'Brak wzmianki o toksyczności nie oznacza G0.'),
        'death': ('1 wymaga daty zgonu; 0 wymaga pustej daty.', 'Nie wolno ustalać statusu z samego braku daty.'),
        'death_date': ('ISO; po rozpoczęciu RT i nie przed ostatnim PSA.', 'Pusta komórka poprawna wyłącznie przy death=0.'),
        'notes': ('Bez PESEL; rozproszone dane strukturalne przenieść po uzgodnieniu.', 'Nie rozpoznawać cukrzycy wyłącznie na podstawie nazwy leku.'),
        'diabetes': ('0/1 według udokumentowanego wywiadu.', 'Brak informacji = null, nie 0.'),
        'hypertension': ('0/1 według udokumentowanego wywiadu.', 'Pojedynczy pomiar ciśnienia nie rozstrzyga rozpoznania.'),
        'smoking': ('never/former/current.', 'Nie pali od 10 lat = former; samo nie pali nie rozstrzyga never/former.')
    }
    rows = []
    for variable, label in zip(COLUMNS, labels):
        typ, unit, allowed, low, high = 'tekst', '', '', '', ''
        if variable in categories:
            typ, allowed = 'kategoria', categories[variable]
        elif variable in binary:
            typ, allowed, low, high = 'logiczna', '0|1', 0, 1
        elif variable in ranges:
            typ = 'liczba_calkowita' if variable in integers else 'liczba'
            low, high, unit = ranges[variable]
        elif variable.endswith('_date'):
            typ, allowed = 'data', 'RRRR-MM-DD'
        rule, note = details.get(variable, ('Wartość zgodna z typem, jednostką i zakresem słownika.', 'Próg kontroli jakości, nie próg rozpoznania klinicznego.'))
        rows.append([variable, label, typ, unit, allowed, low, high, 'pusta komórka; w ekstrakcji null', rule, note])
    return pd.DataFrame(rows, columns=['zmienna', 'etykieta', 'typ', 'jednostka', 'dozwolone_wartosci', 'zakres_min', 'zakres_max', 'kod_braku', 'regula_walidacyjna', 'uwagi'])


def make_dirty(clean, layout=None):
    layout = make_layout() if layout is None else layout
    dirty = clean.astype(object).copy()
    clean = clean.iloc[layout].reset_index(drop=True)
    events = []
    def inject(i, v, value, category, detect, decision='zapytanie_do_osrodka', reason='Zweryfikować zapis w źródle; nie odtwarzać wartości z rozkładu kohorty.', difficulty='latwy'):
        row = int(layout[i])
        assert text_value(clean.at[i, v]) != text_value(value)
        dirty.at[row, v] = value
        events.append(dict(error_id=f'E-{len(events)+1:03d}', patient_id_w_pliku='', wiersz_excel=row+2,
                           zmienna=v, wartosc_w_pliku=text_value(value), wartosc_prawdziwa=text_value(clean.at[i, v]),
                           kategoria=category, jak_wykryc=detect, decyzja=decision, uzasadnienie=reason,
                           wykrywalne_regula=1, trudnosc=difficulty))
    inject(0, 'patient_id', invalid_pesel(clean.at[0, 'birth_date'], 'M', 101), 'identyfikator', '11 cyfr zamiast PR-xxx.', 'usun_identyfikator', 'Usunąć numer osobowy; odzyskać kod badania z ośrodka.')
    for i in [1, 2]:
        inject(i, 'notes', clean.at[i, 'notes'] + ' PESEL: ' + invalid_pesel(clean.at[i, 'birth_date'], 'M', 102+i), 'prywatnosc', '11 cyfr w notes.', 'usun_identyfikator', 'Usunąć identyfikator osobowy; zachować kliniczną część uwag.')
    inject(13, 'patient_id', 'pr 014', 'identyfikator', 'Wzorzec identyfikatora.', 'napraw_wg_slownika', 'Jednoznaczna normalizacja do PR-014.')
    inject(4, 'patient_id', clean.at[3, 'patient_id'], 'duplikat', 'Ten sam ID przy różnych danych.', reason='Uzgodnić oba rekordy; nie scalać ich automatycznie.', difficulty='sredni')
    for i, val in zip([6,7,8,9], ['mężczyzna', '1', 'male', 'K']):
        inject(i, 'sex', val, 'kodowanie', 'Płeć w rejestrze ma wyłącznie kod M.', 'zapytanie_do_osrodka' if val in {'1','K'} else 'napraw_wg_slownika', 'K jest błędem w tym rejestrze. Kod 1 bez mapowania wymaga źródła; jednoznaczne synonimy M można ujednolicić.')
    for i,v,val in [(10,'psa_last_ng_ml',999), (11,'hemoglobin_g_dl',-9), (12,'testosterone_ng_dl','nd'), (14,'creatinine_mg_dl','b.d.'), (15,'weight_kg','brak'), (16,'gi_toxicity_max','-')]:
        inject(i,v,val,'brak_danych','Ukryty brak w polu wymaganym.', reason='Zakodować brak po wyjaśnieniu; nie zastępować zerem ani wartością z czystego klucza.')
    inject(17,'psa_nadir_ng_ml','<0,01','liczba_jako_tekst','Wynik poniżej oznaczalności zamiast pomiaru punktowego.', reason='Uzgodnić kodowanie wartości cenzorowanych. Nie zamieniać na 0 ani 0,005 bez jawnej decyzji protokołu.', difficulty='trudny')
    for i,v,val in [(18,'diagnosis_date','03.04.2025'),(19,'rt_start_date','04/03/2025'),(20,'psa_last_date','2025.04.03'),(21,'diagnosis_date','kwiecień 2025'),(22,'psa_last_date',45750)]:
        inject(i,v,val,'format_daty','Pełna data ISO wymagana przez słownik.', 'napraw_wg_slownika' if i in {18,20} else 'zapytanie_do_osrodka',
               'Polski zapis z kropkami jednoznaczny.' if i in {18,20} else 'Ukośnik bez deklaracji porządku dat, niepełny miesiąc albo numer seryjny Excela wymagają źródła; potwierdzić system 1900/1904.', 'sredni')
    inject(23,'psa_last_date',(date.fromisoformat(clean.at[23,'rt_start_date'])-timedelta(days=1)).isoformat(),'logika_czasowa','PSA obserwacyjne przed RT.')
    inject(24,'death_date',(date.fromisoformat(clean.at[24,'rt_start_date'])-timedelta(days=1)).isoformat(),'logika_czasowa','Zgon przed RT.')
    inject(25,'diagnosis_date',(date.fromisoformat(clean.at[25,'rt_start_date'])+timedelta(days=30)).isoformat(),'logika_czasowa','Rozpoznanie po pierwszej frakcji RT.')
    for i in [26,27,28]:
        inject(i,'creatinine_mg_dl',f"{clean.at[i,'creatinine_mg_dl']*88.4:.1f}".replace('.',','),'jednostka','Kreatynina poza zakresem mg/dl; podejrzenie µmol/l.', reason='W generatorze znana jednostka µmol/l; w pliku bez jednostki konieczne potwierdzenie, następnie ÷88,4.', difficulty='sredni')
    for i in [29,30]:
        inject(i,'hemoglobin_g_dl',f"{clean.at[i,'hemoglobin_g_dl']*.6206:.1f}".replace('.',',')+' mmol/l','jednostka','Jawna jednostka mmol/l w polu g/dl.', 'napraw_wg_slownika','Podzielić przez 0,6206; zachować dokładność 0,01 g/dl.', 'sredni')
    inject(31,'testosterone_ng_dl','0,6 nmol/l','jednostka','Jawna jednostka nmol/l w polu ng/dl.', 'napraw_wg_slownika','Pomnożyć przez 28,84; zaokrąglić do 0,1 ng/dl.', 'sredni')
    inject(32,'weight_kg','180,7791 lb','jednostka','Jednostka lb w polu kg.', 'napraw_wg_slownika','Pomnożyć przez 0,45359237; zaokrąglić do 0,1 kg.', 'sredni')
    for i,v,val in [(33,'psa_dx_ng_ml','12,4 ng/ml'),(34,'psa_last_ng_ml','ok. 0,2'),(35,'rt_dose_gy','78 Gy')]:
        inject(i,v,val,'liczba_jako_tekst','Jednostka lub dopisek w polu liczbowym.', 'zapytanie_do_osrodka' if i==34 else 'napraw_wg_slownika', 'Wpis ok. wymaga potwierdzenia dokładności; jawne jednostki zgodne ze słownikiem można oddzielić od liczby.')
    inject(36,'gleason_score','03.kwi','format_daty','Autokonwersja Gleasona 3-4 w datę.', reason='Z daty nie odtwarzać automatycznie wzorców; porównać pełny wynik histopatologiczny.', difficulty='trudny')
    inject(37,'rt_dose_gy','60/20','struktura','Dawka i liczba frakcji w jednej komórce.', 'napraw_wg_slownika','Dawka 60 Gy i 20 frakcji są jednoznaczne i zgodne z polem rt_fractions.', 'sredni')
    for i,v,val in [(38,'psa_dx_ng_ml',-2),(39,'gu_toxicity_max',7),(40,'rt_dose_gy',780),(41,'weight_kg',9)]:
        inject(i,v,val,'zakres','Wartość poza zakresem słownika.')
    for i,v,val,desc in [(42,'gleason_score',8,'Suma wzorców 4+3 wynosi 7, nie 8.'),
                         (43,'isup_grade',2,'4+3 odpowiada ISUP 3.'),
                         (44,'risk_group','niskie','PSA 25 wymaga grupy wysokiego ryzyka wg protokołu.'),
                         (45,'rt_technique','SBRT','SBRT przy 39 frakcjach.'),
                         (46,'adt',0,'ADT=0 przy zaplanowanych 6 miesiącach.'),
                         (47,'bcr_phoenix',0,'Ostatnie PSA ≥ nadir + 2.'),
                         (48,'death',1,'Zgon bez daty.'),
                         (49,'death',0,'Data zgonu przy statusie żyje.')]:
        inject(i,v,val,'spojnosc_pol',desc, reason='Reguła wskazuje sprzeczność; ustalić, które pole wymaga poprawy w dokumentacji źródłowej.', difficulty='sredni')
    for i,v,val in [(50,'rt_technique','vmat'),(51,'ct_stage','T2 b'),(52,'rt_technique','IMRT '),(53,'smoking','tak'),(54,'smoking','nie'),(55,'smoking','okazjonalnie')]:
        inject(i,v,val,'kategoria','Wartość spoza zamkniętego słownika.', 'napraw_wg_slownika' if i<53 else 'zapytanie_do_osrodka', 'Normalizacja techniki lub T jest jednoznaczna; tak/nie/okazjonalnie nie rozstrzygają historii palenia.')
    inject(56,'notes','NT; DM2; metformina 2x1000; ASA','struktura','Kilka informacji strukturalnych w notes.', reason='Uzgodnić z hypertension i diabetes; oddzielić wywiad i leki.', difficulty='sredni')
    duplicate = clean.iloc[[75]].astype(object).copy()
    duplicate.loc[:, 'patient_id'] = 'PR-121'
    dirty = pd.concat([dirty, duplicate], ignore_index=True)
    events.append(dict(error_id=f'E-{len(events)+1:03d}',patient_id_w_pliku='PR-121',wiersz_excel=122,zmienna='patient_id',wartosc_w_pliku='PR-121',wartosc_prawdziwa='',kategoria='duplikat',jak_wykryc='Wszystkie pola poza ID identyczne z PR-076; dodatkowy rekord.',decyzja='zapytanie_do_osrodka',uzasadnienie='Po potwierdzeniu usunąć cały dodatkowy rekord; nie nadawać mu ID PR-076.',wykrywalne_regula=1,trudnosc='trudny'))
    for e in events:
        e['patient_id_w_pliku'] = text_value(dirty.at[e['wiersz_excel']-2,'patient_id'])
    assert len(events)==56 and len({(e['wiersz_excel'],e['zmienna']) for e in events})==56
    return dirty, pd.DataFrame(events, columns=KEY_COLUMNS)


def make_traps(clean, layout):
    examples = [
        (90, 'rt_dose_gy', 'SBRT 36,25 Gy/5 fr., czyli 7,25 Gy/fr.; schemat dopuszczony protokołem.'),
        (91, 'birth_date', 'Wiek dokładnie 89 lat przy RT 2021-04-03; nie usuwać jako odstającego.'),
        (92, 'psa_dx_ng_ml', 'PSA 148 ng/ml przy cN1; wysokie, ale możliwe; grupa wysokiego ryzyka.'),
        (93, 'gu_toxicity_max', 'Udokumentowane zatrzymanie moczu wymagające cewnikowania podczas RT; prawdziwy odczyn G3.'),
        (94, 'testosterone_ng_dl', 'Pomiar 12 dni po pierwszym podaniu agonisty LHRH, w pierwszym miesiącu ADT; jednostka ng/dl potwierdzona w notes.')
    ]
    rows = []
    for source, variable, reason in examples:
        row = int(layout[source])
        rows.append(dict(patient_id=clean.at[row, 'patient_id'], wiersz_excel=row+2,
                         zmienna=variable, wartosc=text_value(clean.at[row, variable]), uzasadnienie=reason))
    return pd.DataFrame(rows)


def make_rules(dictionary):
    numeric_fields = dictionary[dictionary.typ.isin(['liczba', 'liczba_calkowita'])].zmienna.tolist()
    date_fields = dictionary[dictionary.typ=='data'].zmienna.tolist()
    required = [v for v in COLUMNS if v not in {'death_date','notes'}]
    rules=[]
    def add(rid,desc,typ,variables,control=None,expression=None,**params):
        r=dict(id=rid,opis=desc,typ=typ,zmienne=variables,powaga='ostrzezenie')
        if control:
            r['kontrola']=control
        if expression:
            r['wyrazenie']=expression
        r.update(params)
        rules.append(r)
    pattern=r'PR-(?:00[1-9]|0[1-9][0-9]|1[01][0-9]|120)'
    add('id_format','Kod pacjenta: PR-001..PR-120; bez numerów osobowych.','format',['patient_id'],'format_id',f"~patient_id.str.fullmatch('{pattern}')",wzorzec=pattern)
    add('id_unikalny','Każdy kod pacjenta ma być unikalny; wyjaśnić oba powtarzające się wpisy.','unikalnosc',['patient_id'],'unikalny_id',"patient_id.duplicated(keep=False)")
    add('rekord_duplikat','Dodatkowy rekord identyczny we wszystkich polach poza ID: podejrzenie duplikatu.','unikalnosc',['patient_id'],'duplikat_rekordu',"patient_id.duplicated(keep=False)",uwagi='Kontrola porównuje wszystkie kolumny poza patient_id; samo wyrażenie identyfikatora jest kontrolą pomocniczą.')
    add('prywatnosc','Sekwencja 11 cyfr w ID lub notes wymaga usunięcia identyfikatora osobowego.','format',['patient_id','notes'],'prywatnosc',"patient_id.str.contains(r'(?<!\\d)\\d{11}(?!\\d)') | notes.str.contains(r'(?<!\\d)\\d{11}(?!\\d)')")
    add('brak','Puste wymagane pole albo ukryty brak: brak, nd, b.d., -, 999, -9.','format',['*'],'brak',"psa_last_ng_ml.isin(['', 'brak', 'nd', 'b.d.', '-', '999', '-9'])",uwagi='Kontrola obejmuje wszystkie wymagane pola, nie tylko przykładową kolumnę wyrażenia.')
    for row in dictionary.itertuples():
        if row.typ in {'kategoria','logiczna'}:
            allowed=row.dozwolone_wartosci.split('|')
            add(f'kategoria_{row.zmienna}',f'{row.etykieta}: dokładnie {row.dozwolone_wartosci}.','format',[row.zmienna],'kategoria',f'~{row.zmienna}.isin({allowed!r})')
        if row.typ in {'liczba','liczba_calkowita'}:
            add(f'zakres_{row.zmienna}',f'{row.etykieta}: {row.zakres_min}–{row.zakres_max} {row.jednostka}; próg kontroli jakości.','zakres',[row.zmienna],zakres={'min':row.zakres_min,'max':row.zakres_max})
    add('liczba_format','Liczba bez jednostki, dopisku, przedziału; separator dziesiętny: kropka.','format',numeric_fields,'liczba_format',"~psa_last_ng_ml.str.fullmatch(r'[-+]?(?:\\d+(?:\\.\\d+)?|\\.\\d+)')",uwagi='Ten sam wzorzec stosowany do wszystkich wymienionych pól liczbowych.')
    add('liczba_calkowita','Wzorce Gleasona, ISUP, frakcje, miesiące ADT i stopień CTCAE muszą być całkowite.','format',dictionary[dictionary.typ=='liczba_calkowita'].zmienna.tolist(),'calkowita','rt_fractions % 1 != 0')
    add('data_iso','Data pełna, istniejąca, w formacie RRRR-MM-DD.','format',date_fields,'data_iso',"~rt_start_date.str.fullmatch(r'\\d{4}-\\d{2}-\\d{2}')",uwagi='Kontrola dodatkowo sprawdza istnienie daty i każde pole datowe; death_date puste przy death=0 jest dopuszczalne.')
    add('jednostka','Jednostki inne niż w nazwie pola: kreatynina µmol/l, Hb mmol/l, testosteron nmol/l, masa lb; wynik bez jednostki wymaga potwierdzenia.','format',['creatinine_mg_dl','hemoglobin_g_dl','testosterone_ng_dl','weight_kg'],'jednostka',"creatinine_mg_dl > 15",uwagi='Kontrola obejmuje jawne dopiski jednostek w każdym z wymienionych pól; Hb lub testosteron w innej jednostce bez dopisku mogą być niewykrywalne.')
    add('oznaczalnosc','PSA z zapisem < wymaga ustalenia kodowania wartości poniżej progu; nie podstawiać zera.','format',['psa_nadir_ng_ml','psa_last_ng_ml'],'ponizej_oznaczalnosci',"psa_nadir_ng_ml.str.startswith('<') | psa_last_ng_ml.str.startswith('<')")
    add('autokonwersja','Wynik Gleasona zamieniony przez Excel w datę (kwi/Apr) wymaga źródła.','format',['gleason_score'],'autokonwersja',"gleason_score.str.contains('kwi|Apr', case=False)")
    add('struktura','Dawka/frakcje w jednej komórce lub skróty chorób i leków w notes: rozdzielić po uzgodnieniu.','format',['rt_dose_gy','notes'],'struktura',"rt_dose_gy.str.contains('/') | notes.str.contains('NT;.*DM2;')")
    add('wiek','Wiek w dniu pierwszej frakcji 18–105 lat. Wiek 89 lat jest dopuszczalny.','czas',['birth_date'],'wiek',"birth_date >= rt_start_date",min=18,max=105)
    add('daty','Rozpoznanie ≤ początek RT < ostatnie PSA ≤ zgon.','czas',['diagnosis_date','rt_start_date','psa_last_date','death_date'],'daty',"diagnosis_date > rt_start_date | psa_last_date <= rt_start_date | (death_date != '' & death_date < psa_last_date)",kolejnosc=[['birth_date','diagnosis_date'],['diagnosis_date','rt_start_date'],['rt_start_date','psa_last_date'],['rt_start_date','death_date'],['psa_last_date','death_date']])
    add('gleason','Suma Gleasona musi odpowiadać sumie obu wzorców.','spojnosc',['gleason_score'],'gleason','gleason_score != gleason_primary + gleason_secondary')
    add('isup','ISUP: 3+3→1; 3+4→2; 4+3→3; suma 8→4; suma 9–10→5.','spojnosc',['isup_grade'],'isup',"(gleason_primary == 3 & gleason_secondary == 3 & isup_grade != 1) | (gleason_primary == 3 & gleason_secondary == 4 & isup_grade != 2) | (gleason_primary == 4 & gleason_secondary == 3 & isup_grade != 3) | (gleason_primary + gleason_secondary == 8 & isup_grade != 4) | (gleason_primary + gleason_secondary >= 9 & isup_grade != 5)")
    high="(psa_dx_ng_ml > 20 | isup_grade >= 4 | ct_stage.isin(['T2c','T3a','T3b','T4']) | cn_stage == 'N1')"
    low="(psa_dx_ng_ml < 10 & isup_grade == 1 & ct_stage.isin(['T1c','T2a']) & cn_stage == 'N0')"
    add('ryzyko',PROTOCOL['ryzyko'],'spojnosc',['risk_group'],'ryzyko',f"({high} & risk_group != 'wysokie') | (~{high} & {low} & risk_group != 'niskie') | (~{high} & ~{low} & risk_group != 'posrednie')",ct_dozwolone=['T1c','T2a','T2b','T2c','T3a','T3b','T4'],ct_wysokie=['T2c','T3a','T3b','T4'])
    schedules=[[78,39],[76,38],[60,20],[62,20],[70,28],[36.25,5],[40,5]]
    expr='~('+' | '.join(f'(rt_dose_gy == {d} & rt_fractions == {f})' for d,f in schedules)+')'
    add('schemat_rt','Dawka na prostatę i frakcje muszą tworzyć jeden z siedmiu schematów protokołu.','spojnosc',['rt_dose_gy','rt_fractions'],'schemat_rt',expr,schematy=schedules)
    add('sbrt','SBRT wtedy i tylko wtedy, gdy pięć frakcji. 36,25 Gy/5 fr. jest poprawne.','spojnosc',['rt_technique','rt_fractions'],'sbrt',"(rt_technique == 'SBRT' & rt_fractions != 5) | (rt_technique != 'SBRT' & rt_fractions == 5)")
    add('adt',PROTOCOL['adt'],'spojnosc',['adt','adt_months'],'adt','(adt == 0 & adt_months != 0) | (adt == 1 & adt_months == 0)',wysokie_min=18,wysokie_max=36,posrednie_typowo=6)
    add('phoenix',PROTOCOL['phoenix'],'spojnosc',['bcr_phoenix'],'phoenix','(psa_last_ng_ml >= psa_nadir_ng_ml + 2 & bcr_phoenix != 1) | (psa_last_ng_ml < psa_nadir_ng_ml + 2 & bcr_phoenix != 0)',przyrost=2)
    add('nadir','Nadir po RT nie może przekraczać ostatniego PSA.','spojnosc',['psa_nadir_ng_ml','psa_last_ng_ml'],'nadir','psa_nadir_ng_ml > psa_last_ng_ml')
    add('zgon','death=1 wymaga daty; death=0 wymaga pustej daty. Wyjaśnić oba pola.','spojnosc',['death','death_date'],'zgon',"(death == 1 & death_date == '') | (death == 0 & death_date != '')")
    return {'wersja':2,'scenariusz':'PROSTATA-RT','uwagi':'wyrazenie: naruszenie (True); zakres: dozwolone granice. Kontrole wielopolowe i formatowe mają jawny identyfikator kontrola oraz parametry. Walidator korzysta z tych parametrów i słownika, pomija wnioskowanie z brakujących lub niemożliwych pomiarów. Wyrażenia agregatowe są pomocnicze; pełne działanie jest opisane przez kontrola, zmienne i parametry.','reguly':rules}


def polish_number(value,precision=None):
    return (format(value,f'.{precision}f') if precision is not None else text_value(value)).replace('.',',')


def display_date(value,style):
    return date.fromisoformat(value).strftime(['%Y-%m-%d','%d.%m.%Y','%d/%m/%Y','%Y.%m.%d'][style%4])


def schema_object(dictionary):
    properties={}
    for v in EXTRACT:
        r=dictionary.set_index('zmienna').loc[v]
        item={'description':r.etykieta+(' ['+r.jednostka+']' if r.jednostka else '')}
        if r.typ in {'tekst','kategoria','data'}:
            item['type']=['string','null']
            if r.typ=='kategoria':
                item['enum']=r.dozwolone_wartosci.split('|')+[None]
            if r.typ=='data':
                item.update(format='date',pattern=r'^\d{4}-\d{2}-\d{2}$')
            if v=='patient_id':
                item['pattern']=r'^PR-(?:00[1-9]|0[1-9][0-9]|1[01][0-9]|120)$'
        elif r.typ=='logiczna':
            item.update(type=['integer','null'],enum=[0,1,None])
        else:
            item.update(type=['integer' if r.typ=='liczba_calkowita' else 'number','null'],minimum=float(r.zakres_min),maximum=float(r.zakres_max))
        properties[v]=item
    return {'$schema':'https://json-schema.org/draft/2020-12/schema','title':'PROSTATA-RT — ekstrakcja danych syntetycznych','type':'object','additionalProperties':False,'required':EXTRACT,'properties':properties}
def make_documents(clean):
    folder=DATA/'dokumenty'
    folder.mkdir(parents=True,exist_ok=True)
    gold, evidence, difficulties=[],[],[]
    # Różne narracje i układy: pełny wypis, list do urologa, notatka problemowa,
    # wpis ambulatoryjny, konsultacja z późniejszym uzupełnieniem, raport tabelaryczny.
    stories=[
        'Przed symulacją wykonano ocenę zalegania moczu. Chory otrzymał instrukcję przygotowania pęcherza i odbytnicy; powtórzył zalecenia własnymi słowami. Codzienną lokalizację prostaty prowadzono na obrazach CBCT. Omówiono możliwość przejściowego nasilenia częstomoczu i odróżnienie objawów infekcji od odczynu popromiennego.',
        'Pacjent skierowany przez urologa po biopsji celowanej i systematycznej. Opis mpMR zestawiono z wynikiem histopatologicznym; nie przypisano wyższego stopnia z samego obrazu radiologicznego. Po omówieniu metod radykalnych chory wybrał napromienianie. Poniżej dopisano dane z zakończonego leczenia i późniejszej kontroli rejestru.',
        'Wizyta dotyczy oceny onkologicznej i następstw leczenia. Aktualne dolegliwości oddzielono od maksymalnego odczynu w całym okresie obserwacji. W dzienniczku mikcji pacjent zapisuje także spożycie płynów. Wyniki PSA przepisano z datowanych wydruków laboratoryjnych; zestawienia bez dat nie wykorzystano do oceny trendu.',
        'Leczenie wykonano z weryfikacją ułożenia przed każdą frakcją. Korekty pozycji odnotowano w systemie terapeutycznym. Nie stwierdzono konieczności ponownej symulacji z powodu zmiany anatomii. Chory otrzymał wypis z zestawieniem dawki na prostatę; dawki w innych objętościach nie są wartościami tej kolumny rejestru.',
        'Konsultację przeprowadzono z udziałem osoby bliskiej na prośbę chorego. Omówiono możliwość leczenia operacyjnego i radioterapii oraz spodziewane następstwa ADT. Rozmowę o funkcji seksualnej udokumentowano osobno. W tej kopii pominięto część wywiadu internistycznego; brak zapisu nie oznacza wykluczenia danej choroby.',
        'Pacjent przyniósł wyniki z dwóch laboratoriów. Przed porównaniem zweryfikowano datę pobrania i jednostki. Wartości przedstawione poniżej odnoszą się do konkretnego pomiaru, a nie do mediany z kilku badań. Sam wzrost PSA wymaga oceny w kontekście nadiru i wcześniejszej hormonoterapii.',
        'Dokument sporządzono na zakończenie napromieniania; część o obserwacji uzupełniono później z kart ambulatoryjnych. Zalecenia dotyczące leków na objawy mikcyjne przekazano urologowi. Maksimum toksyczności zapisano w skali CTCAE, bez utożsamiania go z nasileniem dolegliwości w dniu ostatniego badania PSA.',
        'Przy kwalifikacji oceniono sprawność ogólną, wywiad mikcyjny i możliwość dojazdów na leczenie. Pacjent był samodzielny. Opis rozsiewu oparto na badaniach obrazowych; nie wyciągano wniosków wyłącznie ze stężenia PSA. Ten wpis zawiera również datowane uzupełnienie z późniejszej obserwacji po zakończeniu RT.',
        'Kontrola odbyła się planowo. Omówiono znaczenie regularnych oznaczeń PSA i potrzebę przekazywania pełnego wyniku z jednostką. Przy ocenie tolerancji oddzielono objawy ze strony dróg moczowych od przewodu pokarmowego. Kwalifikacja nawrotu w rejestrze dotyczy wyłącznie kryterium biochemicznego, nie potwierdzenia lokalizacji choroby.',
        'Do planowania wykorzystano obrazy tomografii i rezonansu. Oceniono odtwarzalność wypełnienia pęcherza oraz obecność gazów w odbytnicy. Zalecenia przygotowania dopasowano do możliwości chorego. W dokumentacji pozostawiono oddzielnie technikę, dawkę całkowitą i liczbę frakcji, aby nie mylić schematu z dawką pojedynczej frakcji.',
        'Chory pytał o różnicę między oceną histopatologiczną a kliniczną grupą ryzyka. Wyjaśniono, że wynik biopsji, PSA i cTN wpływają na kwalifikację wspólnie. Decyzję terapeutyczną omówiono po przedstawieniu dostępnych opisów. Uzupełnienie po leczeniu zapisano na końcu tej samej karty, z podaniem źródła laboratoryjnego.',
        'W trakcie wizyty przejrzano dokumenty z ośrodka prowadzącego oraz zestawienie kolejnych pomiarów PSA. Nie uśredniano pomiarów wykonanych w różnych dniach. Maksymalny odczyn GU i GI pochodzi z całego okresu RT i obserwacji. Wyniki laboratoryjne zachowano w jednostkach podanych na oryginalnym wydruku.',
        'Wypis zawiera dawkę na prostatę. Przy zajęciu regionalnych węzłów zakres napromieniania ustalano w planie osobno; pole dawki rejestru nie opisuje dawki na węzły. Chory otrzymał zalecenie dalszej współpracy z urologiem i przekazywania informacji o nietolerancji hormonoterapii oraz o zatrzymaniu moczu.',
        'W skierowaniu podano wiek orientacyjny. W rozmowie potwierdzono datę urodzenia zapisaną w nagłówku; ten zapis przyjęto do rejestru. Omówiono plan leczenia i kolejność konsultacji. Informacje o późniejszym PSA dołączono z poradni kontrolnej, aby nie traktować ich jako danych dostępnych w dniu kwalifikacji.',
        'Pacjent zgłasza się z segregatorem wyników. Zestawiono nadir z ostatnim oznaczeniem bez zaokrąglania różnicy do pełnych jednostek. W przypadku osiągnięcia progu Phoenix wynik rejestru oznacza spełnienie definicji biochemicznej. Dalsze postępowanie zależy od całego obrazu choroby; ta karta nie rozstrzyga miejsca ewentualnego nawrotu.',
        'W dokumentacji histopatologicznej znaleziono różne oznaczenia ISUP. Uzyskany aneks podpisany przez patomorfologa wyraźnie koryguje wcześniejszy skrót. Do rejestru przyjęto wynik po korekcie. Informację o rozbieżności zachowano w opisie, aby odbiorca nie wybierał automatycznie pierwszej liczby występującej w dokumencie.',
        'W kopiach dokumentów występują sprzeczne oznaczenia ISUP. Nie dołączono aneksu ani wyniku ponownej oceny preparatów. Zgłoszono potrzebę wyjaśnienia rozbieżności u źródła. Pozostałe jawnie podane dane można przepisać, lecz nie należy samodzielnie nadawać rozstrzygającego stopnia ISUP na podstawie domniemanej hierarchii źródeł.',
        'Dostarczony wynik PSA zawiera jedynie określenie poniżej granicy oznaczalności. Nie zamieniono go na zero, ponieważ nie jest to wynik punktowy. Brak porównywalnego pomiaru wpływa na możliwość obliczenia zmiennej Phoenix. W pozostałym zakresie oddzielono dane opisane wprost od informacji nieobecnych w karcie.',
        'Na dwóch stronach kopii wpisano różne daty urodzenia. Nie ma dokumentu wskazującego, który zapis poprawiono. Numer PESEL jest fikcyjny i nie służy do odtwarzania daty. Rozbieżność wymaga uzgodnienia przed uzupełnieniem tej zmiennej; nie przeszkadza w odczytaniu jednoznacznie podanych parametrów leczenia.',
        'Dokument jest kopią skróconej karty kontroli. Część pól dotyczących nadiru i planowanego czasu ADT nie została przeniesiona. Nie przypisano zera do brakujących informacji. Rozpoznania towarzyszące przepisano tylko z jednoznacznego wywiadu; same nazwy leków nie stanowią wystarczającej podstawy do uzupełnienia wszystkich chorób.',
        'Wizyta kontrolna w trakcie długoterminowej hormonoterapii uzupełniającej. Chory zgłasza dobrą tolerancję leczenia, z okresowymi uderzeniami gorąca o łagodnym nasileniu. Przygotowanie pęcherza i odbytnicy w trakcie RT oceniono jako optymalne na podstawie archiwalnych skanów CBCT.',
        'Chory leczony w trybie ambulatoryjnym z zastosowaniem fotonów 6 MV. Napromienianie loży stercza prowadzono z codzienną kontrolą ułożenia IGRT. Tolerancja wczesna leczenia była zadowalająca, bez konieczności przerw terapeutycznych. Zalecenia dietetyczne utrzymano do zakończenia obserwacji.',
        'Konsultacja kwalifikacyjna przeprowadzona po wieloparametrycznym rezonansie miednicy i biopsji fuzyjnej. Przedstawiono choremu korzyści oraz ryzyko powikłań leczenia radykalnego. Z uwagi na obecność chorób współistniejących wybrano napromienianie skojarzone z deprywacją androgenową. Dane z obserwacji dopisano po zakończeniu RT.',
        'Ocena kliniczna w 18. miesiącu po zakończeniu radioterapii. Chory neguje krwiomocz, bóle podbrzusza oraz dolegliwości ze strony dolnego odcinka przewodu pokarmowego. Czynność trzymania moczu zachowana całkowicie. Zalecono utrzymanie umiarkowanej aktywności fizycznej.',
        'Plan leczenia zrealizowano techniką intensywnej modulacji wiązki IMRT. Rozkład dawek w narządach krytycznych spełniał protokołowe kryteria QUANTEC dla pęcherza moczowego i przedniej ściany odbytnicy. Wypis zawiera parametry dawki na stercz; wywiad dotyczący palenia tytoniu nie został w tej karcie odnotowany.',
        'Pacjent skierowany z poradni rejonowej z podejrzeniem raka stercza wysokiego ryzyka. Badanie per rectum wykazało asymetrię prawego płata bez ewidentnego naciekania pęczków naczyniowo-nerwowych. Poniżej zamieszczono zestawienie badań biopsyjnych oraz późniejsze wpisy z przebiegu leczenia i kontroli PSA.',
        'Okresowa kontrola w poradni onkologicznej. Analiza dynamiki stężenia PSA wskazuje na stabilną odpowiedź biochemiczną. Zgłaszany sporadycznie nykturia bez cech przeszkody podpęcherzowej. Z powodu braku świeżego wyniku stężenia kreatyniny zalecono kontrolne badanie laboratoryjne w rejonie.',
        'Radykalne napromienianie zrealizowano zgodnie z planem bez przerw technicznych. W trakcie leczenia chory przyjmował profilaktycznie tamsulosynę z dobrą tolerancją. Przed każdą frakcją weryfikowano wypełnienie pęcherza metodą ultrasonograficzną w pracowni teleradioterapii.',
        'Kwalifikacja do radioterapii radykalnej po konsylium wielodyscyplinarnym. Chory poinformowany o możliwości leczenia chirurgicznego, ostatecznie zdecydował o napromienieniu IMRT. W karcie zamieszczono podsumowanie wyjściowych badań obrazowych oraz uzupełniające dane z przebiegu późniejszej obserwacji.',
        'Wizyta kontrolna po radiochirurgii stereotaktycznej SBRT. Chory bez cech ostrej lub późnej toksyczności popromiennej. Badanie laboratoryjne hemoglobiny nie zostało wykonane w ostatnim kwartale z powodu trudności technicznych w punkcie pobrań. Parametry mikcyjne pozostają w normie.',
        'Zakończono radykalną radioterapię hipofrakcjonowaną VMAT. Ze względu na wyjściową grupę wysokiego ryzyka włączono analog LHRH w schemacie długoterminowym. W karcie zestawiono parametry fizyczne napromieniania; dane laboratoryjne i daty pobrań odnotowano z oryginalnych załączników.',
        'Chory zgłosił się z wynikami biopsji systematycznej prostaty. W wywiadzie internistycznym nie odnotowano informacji o cukrzycy; pozostałe obciążenia udokumentowano na podstawie karty informacyjnej lekarza POZ. Uzupełnienie danych po radioterapii dopisano po weryfikacji dokumentacji ambulatoryjnej.',
        'Wizyta kontrolna po skojarzonym leczeniu radio-hormonalnym. Analiza stężeń PSA potwierdza remisję biochemiczną. Odczyn popromienny ze strony układu pokarmowego oceniono szczegółowo w badaniu podmiotowym; oceny toksyczności moczowo-płciowej GU w tej notatce nie przeprowadzono.',
        'Napromienianie zrealizowano techniką dynamiczną IMRT na przyspieszaczu liniowym z wielolistkowym kolimatorem. Weryfikację izocentrum prowadzono systemem wizualizacji portalowej i CBCT. Pacjent stosował się ściśle do zaleceń dotyczących reżimu płynowego przed zabiegiem.',
        'Wstępna kwalifikacja urologiczna chorego z zaawansowanym miejscowo rakiem stercza cN1. Omówiono konieczność napromieniania elektywnego regionalnych węzłów chłonnych oraz długoterminowej deprywacji androgenowej. Niniejszy wyciąg uzupełniono o retrospektywne dane z kontroli biochemicznej.',
        'Wizyta kontrolna po radioterapii VMAT. W wywiadzie ogólnoustrojowym brak jednoznacznej adnotacji dotyczącej nadciśnienia tętniczego; pomiary ciśnienia w gabinecie pozostawały prawidłowe. Wykonano ocenę wskaźników laboratoryjnych oraz aktualnego stężenia PSA w surowicy.',
        'Karta leczenia promieniami wysokoenergetycznymi. Zastosowano technikę łukową VMAT z modulacją intensywności dawki. Reakcja popromienna wczesna na poziomie śluzówek pęcherza moczowego miała charakter przejściowy i ustąpiła po krótkim leczeniu objawowym.',
        'Konsultacja specjalistyczna po rezonansie magnetycznym miednicy mniejszej. W dokumentacji odnotowano wdrożenie hormonoterapii analogiem LHRH, lecz całkowity zaplanowany czas ADT nie został wyspecyfikowany w skierowaniu. Uzupełnienie o wyniki po RT sporządzono na podstawie kartoteki.',
        'Ocena pooperacyjna i popromienna. W badaniu kontrolnym odnotowano wzrost stężenia PSA powyżej nadiru spełniający kryteria wznowy biochemicznej Phoenix. W dokumentacji oceniono objawy dysuryczne GU; stopnia odczynu żołądkowo-jelitowego GI w badaniu podmiotowym nie sprecyzowano.',
        'Zakończono kurs radioterapii radykalnej gruczołu krokowego. Parametry geometryczne i dozymetryczne planu leczenia zweryfikowano przed rozpoczęciem pierwszej frakcji. Chory tolerował zabiegi bez powikłań wymagających hospitalizacji.',
        'Wizyta kwalifikacyjna w poradni urologicznej. Pacjent z rakiem stercza grupy wysokiego ryzyka zakwalifikowany do napromieniania IMRT z równoczesną hormonoterapią. Poniżej zamieszczono zestawienie badań wyjściowych oraz wyciąg z późniejszej obserwacji ambulatoryjnej.',
        'Rutynowa kontrola po radioterapii radykalnej. Pacjent nie podaje trudności w oddawaniu moczu ani dolegliwości bólowych miednicy. Wyniki badań biochemicznych i hematologicznych przepisano z oryginalnego wydruku szpitalnego.',
        'Teleradioterapia wiązkami fotonowymi o modulowanej intensywności zrealizowana planowo. W trakcie procedury prowadzono codzienną weryfikację pozycji narządów na aparacie terapeutycznym. Wyniki badań laboratoryjnych z dnia przyjęcia dołączono do wypisu.',
        'Wizyta kwalifikacyjna urologa onkologa. Ze względu na brak dostępu do bieżących wyników laboratoryjnych (kreatynina, morfologia) zalecono ich pilne uzupełnienie w poradni rejonowej. Wpis uzupełniono o retrospektywne dane dotyczące radioterapii i monitorowania PSA.',
        'Kontrola onkologiczna po zakończeniu IMRT. W nagłówku wyciągu pominięto dokładną datę urodzenia pacjenta; identyfikację prowadzono na podstawie numeru księgi głównej. Objawy mikcyjne w granicach normy wiekowej.',
        'Karta leczenia promieniami jonizującymi. Leczenie przeprowadzono zgodnie z indywidualnym planem leczenia. Odczyn popromienny wczesny łagodny, bez konieczności modyfikacji dawki frakcyjnej. Zalecono okresowe kontrole urologiczne i oznaczenia PSA.',
        'Konsultacja specjalistyczna z omówieniem wyników biopsji gruboigłowej stercza. Przedstawiono choremu założenia napromieniania hipofrakcjonowanego. Zapis uzupełniono o dane z późniejszego leczenia i wizyt kontrolnych po radioterapii.',
        'Wizyta kontrolna w poradni radioterapii. Odnotowano stabilizację parametrów klinicznych. Wywiad internistyczny zebrano szczegółowo pod kątem chorób metabolicznych i układu krążenia; palenie tytoniu oceniono w wywiadzie.',
        'Radykalna teleradioterapia VMAT ukończona w zaplanowanym czasie. Wypis zawiera podsumowanie dawki pochłoniętej w obszarze tarczowym oraz parametry ochrony pęcherza i odbytnicy. Badania kontrolne zalecono co 3 miesiące.',
        'Kwalifikacja do radioterapii. W dostarczonym wyciągu ambulatoryjnym brakuje jednoznacznego zapisu nadiru PSA po leczeniu, co uniemożliwia ocenę kryterium Phoenix w tej notatce. Pozostałe dane kliniczne przepisano z oryginału.',
        'Kontrola ambulatoryjna po radioterapii skojarzonej z hormonoterapią. Chory kontynuuje leczenie analogiem LHRH; całkowitego zaplanowanego czasu ADT nie określono w aktualnym wpisie. Czynność nerek i parametry czerwonokrwinkowe stabilne.',
        'Napromienianie zrealizowano techniką IMRT. Weryfikację ułożenia przeprowadzano systematycznie zgodnie z wewnętrzną procedurą zapewnienia jakości. Chory zgłaszał przejściowe parcia naglące, które ustąpiły po leczeniu spasmolitycznym.',
        'Konsultacja urologiczna chorego po biopsji fuzyjnej. Wyniki histopatologiczne i obrazowe omówiono szczegółowo. Karta zawiera uzupełnienie z późniejszego przebiegu leczenia radykalnego i obserwacji stężenia PSA w surowicy.',
        'Kontrola onkologiczna. W dokumentacji histopatologicznej stwierdzono rozbieżność opisową wzorców architektonicznych i sumarycznego stopnia ISUP bez dołączonego aneksu korygującego. Pozostałe dane dotyczące leczenia pozostają jednoznaczne.',
        'Karta informacyjna z radioterapii. Pierwotne oznaczenie histopatologiczne ISUP zostało skorygowane podpisanym aneksem patomorfologicznym, który przyjęto do weryfikacji dawki. Przebieg leczenia był niepowikłany.',
        'Konsultacja urologiczna z omówieniem odpowiedzi na leczenie. Ostatnie badanie stężenia PSA wykazało wartość poniżej progu oznaczalności metody laboratoryjnej. Zestawienie uzupełniono o dane z zakończonego napromieniania.',
        'Wizyta kontrolna po radioterapii. W dostarczonych kopiach dokumentów z ośrodka zewnętrznego odnotowano rozbieżność daty urodzenia pacjenta na kolejnych stronach. Przebieg teleradioterapii i monitorowania PSA udokumentowano precyzyjnie.',
        'Karta leczenia promieniami fotonowymi. Wiek orientacyjny podany na skierowaniu różnił się od daty urodzenia ustalonej na podstawie dowodu tożsamości. Napromienianie zrealizowano zgodnie z protokołem planowania 3D/IMRT.',
        'Wizyta urologiczna kwalifikacyjna. Wywiad internistyczny w przekazanym odpisie nie zawierał informacji o cukrzycy ani nadciśnieniu tętniczym. Dołączono uzupełnienie z poradni teleradioterapii dotyczące późniejszej kontroli biochemicznej.',
        'Skrócona karta z wizyty kontrolnej. W dostarczonym fragmencie nie ujęto wartości nadiru PSA ani planowanego czasu trwania hormonoterapii. Oceniono tolerancję leczenia w skali CTCAE oraz aktualne stężenie PSA.'
    ]
    absent={3:['birth_date'],4:['diabetes'],5:['hypertension'],6:['smoking'],7:['creatinine_mg_dl'],
            8:['hemoglobin_g_dl'],9:['psa_nadir_ng_ml','bcr_phoenix'],10:['adt_months'],
            11:['gu_toxicity_max'],14:['gi_toxicity_max'],16:['isup_grade'],
            17:['psa_last_ng_ml','bcr_phoenix'],18:['birth_date'],19:['psa_nadir_ng_ml','adt_months','bcr_phoenix'],
            24:['smoking'], 26:['creatinine_mg_dl'], 29:['hemoglobin_g_dl'], 31:['diabetes'],
            32:['gu_toxicity_max'], 35:['hypertension'], 37:['adt_months'], 38:['gi_toxicity_max'],
            43:['creatinine_mg_dl', 'hemoglobin_g_dl'], 44:['birth_date'], 49:['psa_nadir_ng_ml', 'bcr_phoenix'],
            50:['adt_months'], 53:['isup_grade'], 55:['psa_last_ng_ml', 'bcr_phoenix'],
            56:['birth_date'], 58:['diabetes', 'hypertension'], 59:['psa_nadir_ng_ml', 'adt_months', 'bcr_phoenix']}
    names=['Anzelm','Bogumił','Cyprian','Dobromir','Erazm','Feliks','Gwidon','Hieronim','Iwo','Jarema',
           'Kajetan','Lucjan','Mirosław','Norbert','Olgierd','Przemysław','Radomir','Seweryn','Teodor','Witold',
           'Adam', 'Bartłomiej', 'Cezary', 'Dariusz', 'Edward',
           'Franciszek', 'Grzegorz', 'Henryk', 'Ignacy', 'Jan',
           'Kazimierz', 'Leszek', 'Marek', 'Nikodem', 'Oskar',
           'Paweł', 'Robert', 'Stanisław', 'Tadeusz', 'Wojciech',
           'Aleksander', 'Bogusław', 'Czesław', 'Damian', 'Eugeniusz',
           'Filip', 'Gerard', 'Hubert', 'Jacek', 'Kamil',
           'Leon', 'Mariusz', 'Napoleon', 'Patryk', 'Rafał',
           'Sławomir', 'Tomasz', 'Wacław', 'Zenon', 'Zbigniew']
    easy_docs = {20, 21, 22, 23, 27, 28, 33, 34, 39, 40, 45, 46, 51}
    for j in range(60):
        if j < 20:
            r=clean.iloc[100+j].to_dict()
        else:
            r=clean.iloc[60+(j-20)].to_dict()
        doc=f'DOK-{j+1:02d}.txt'; missing=set(absent.get(j,[]))
        is_easy = (j in easy_docs) if j >= 20 else False
        date_style = (j % 2) if is_easy else j
        answer={v:None if v in missing else r[v] for v in EXTRACT}
        blocks={k:[] for k in ['header','history','pathology','treatment','follow','labs','comorbidity','ending']}
        def add(block,fragment,fields=(),kind='',explanation='Wartość podana wprost.'):
            blocks[block].append(fragment)
            for v in fields:
                assert answer[v] is not None
                evidence.append(dict(dokument=doc,zmienna=v,wartosc_klucza=text_value(answer[v]),fragment=fragment,transformacja=explanation))
                if kind:
                    difficulties.append(dict(dokument=doc,zmienna=v,typ_trudnosci=kind,dlaczego_trudne=explanation))
        kind=j%3
        titles=['KARTA INFORMACYJNA Z LECZENIA RADIOTERAPIĄ','Konsultacja urologiczna kwalifikacyjna — kopia z uzupełnieniem obserwacji','Wizyta kontrolna po radioterapii: PSA i toksyczność']
        add('header',titles[kind]+'\nPROSTATA-RT | OŚRODEK FIKCYJNY | DOKUMENT SYNTETYCZNY DO ĆWICZEŃ')
        add('header',f"{names[j]} Fikcyjny-{j+1:02d}; kod rejestru: {r['patient_id']}. PESEL fikcyjny, błędna cyfra kontrolna: {invalid_pesel(r['birth_date'],'M',200+j)}.",['patient_id'])
        if 'birth_date' not in missing:
            add('header',f"Ur. {display_date(r['birth_date'],date_style)}.",['birth_date'],'data','Normalizacja daty do ISO. Ukośnik w dokumentach oznacza DD/MM/RRRR.')
        elif j in {18, 56}:
            other=(date.fromisoformat(r['birth_date'])+timedelta(days=365)).isoformat()
            add('header',f"Ur. na stronie 1: {display_date(r['birth_date'],1)}; na stronie 2: {display_date(other,1)}. Brak potwierdzenia daty urodzenia.")
        add('history',stories[j])
        if j in {13, 57}:
            age=date.fromisoformat(r['rt_start_date']).year-date.fromisoformat(r['birth_date']).year
            add('history',f'Na skierowaniu wiek {age+4} lat — wpis niezgodny z potwierdzoną datą urodzenia, nie używać go do jej korekty.')
        diag_style = (j+1) % 2 if is_easy else (j+1)
        add('pathology',f"Rozpoznanie ca prostatae z biopsji z {display_date(r['diagnosis_date'],diag_style)}. PSA przy rozpoznaniu: {polish_number(r['psa_dx_ng_ml'])} ng/ml.",['psa_dx_ng_ml'])
        gleason_label=['Gs','Gleason','Wynik biopsji: Gs'][j%3]
        add('pathology',f"{gleason_label} {r['gleason_primary']}+{r['gleason_secondary']}={r['gleason_score']}.",['gleason_primary','gleason_secondary'])
        if j in {15, 54}:
            alt_isup = 2 if r['isup_grade'] != 2 else 1
            add('pathology',f"W karcie przekazanej przez urologa: ISUP {alt_isup}. Aneks histopatologiczny, podpisany i potwierdzony: ISUP {r['isup_grade']}; koryguje wcześniejszy zapis.", ['isup_grade'],'sprzecznosc',f"Przyjąć ISUP {r['isup_grade']} z potwierdzonego aneksu; nie pierwszy wynik {alt_isup}.")
        elif j in {16, 53}:
            alt_isup = 2 if r['isup_grade'] != 2 else 3
            add('pathology',f"Opis wzorców wskazuje {r['gleason_primary']}+{r['gleason_secondary']}={r['gleason_score']}, lecz w podsumowaniu wpisano ISUP {alt_isup}. Sprzeczność nierozstrzygnięta, brak aneksu; ISUP pozostaje nieustalone.")
        else:
            add('pathology',f"ISUP {r['isup_grade']}.",['isup_grade'])
        group={'niskie':'niskie','posrednie':'pośrednie','wysokie':'wysokie'}[r['risk_group']]
        add('pathology',f"Stopień kliniczny: c{r['ct_stage']} c{r['cn_stage']}. Grupa ryzyka w karcie kwalifikacji: {group}.",['ct_stage','cn_stage','risk_group'])
        add('pathology','W PET-PSMA bez cech przerzutów odległych; obecne regionalne węzły oceniono jako cN1.' if r['cn_stage']=='N1' else 'Bez cech przerzutów w PET-PSMA; cN0 w ocenie regionalnych węzłów.')
        rt_labels=['Pierwsza frakcja RT','RT rozpoczęto','Początek napromieniania'][j%3]
        rt_style = (j+2) % 2 if is_easy else (j+2)
        add('treatment',f"{rt_labels}: {display_date(r['rt_start_date'],rt_style)}.",['rt_start_date'],'data','Data pierwszej frakcji; nie data rozpoczęcia ADT.')
        tech=r['rt_technique']
        add('treatment',f"Technika {tech}"+('/IGRT' if tech!='SBRT' else '')+f"; dawka na prostatę {polish_number(r['rt_dose_gy'])} Gy w {r['rt_fractions']} frakcjach.",['rt_technique','rt_dose_gy','rt_fractions'])
        if r['adt']:
            fragment='ADT zastosowano: agonista LHRH.'
            fields=['adt']
            if 'adt_months' not in missing:
                fragment+=f" Zaplanowany łączny czas ADT: {r['adt_months']} mies."
                fields.append('adt_months')
            add('treatment',fragment,fields)
        else:
            add('treatment','ADT nie stosowano.'+(' Zaplanowany łączny czas ADT: 0 mies.' if 'adt_months' not in missing else ''),['adt']+(['adt_months'] if 'adt_months' not in missing else []),'negacja','Jawne niestosowanie ADT oznacza 0; brak planowanego czasu pozostawić null.')
        psa_last_style = (j+3) % 2 if is_easy else (j+3)
        add('follow',f"Kontrolne oznaczenie PSA z {display_date(r['psa_last_date'],psa_last_style)}.")
        if 'psa_nadir_ng_ml' not in missing:
            add('follow',f"Najniższe PSA po RT (nadir): {polish_number(r['psa_nadir_ng_ml'])} ng/ml.",['psa_nadir_ng_ml'])
        if 'psa_last_ng_ml' not in missing:
            add('follow',f"Ostatnie PSA: {polish_number(r['psa_last_ng_ml'])} ng/ml.",['psa_last_ng_ml'])
        elif j in {17, 55}:
            add('follow','Ostatnie PSA: <0,01 ng/ml. Laboratorium nie podało wartości punktowej.')
        if 'bcr_phoenix' not in missing:
            # Dowód to oba pomiary; flagi nie dopisujemy, aby ćwiczyć wyprowadzenie definicji.
            fragment=blocks['follow'][-2]+'\n'+blocks['follow'][-1]
            evidence.append(dict(dokument=doc,zmienna='bcr_phoenix',wartosc_klucza=text_value(answer['bcr_phoenix']),fragment=fragment,transformacja='1 gdy ostatnie PSA ≥ nadir + 2 ng/ml, inaczej 0.'))
        toxic=[]; fields=[]
        for v,label in [('gu_toxicity_max','GU'),('gi_toxicity_max','GI')]:
            if v not in missing:
                toxic.append(f"{label} G{r[v]}");fields.append(v)
        if toxic:
            add('follow','Maksymalny odczyn w całej obserwacji, CTCAE: '+', '.join(toxic)+'.',fields)
        if 'gi_toxicity_max' not in missing and r['gi_toxicity_max']==0:
            add('follow','Bez dolegliwości ze strony przewodu pokarmowego w udokumentowanym okresie obserwacji.')
        lab=[];labfields=[]; conversion=[]
        if 'creatinine_mg_dl' not in missing:
            alt_c = (j%3!=0) if not is_easy else False
            val=polish_number(r['creatinine_mg_dl']*88.4,1) if alt_c else polish_number(r['creatinine_mg_dl'],2)
            lab.append(f"kreatynina {val} {'µmol/l' if alt_c else 'mg/dl'}")
            labfields.append('creatinine_mg_dl');conversion.append('Kreatynina: µmol/l ÷88,4, do 0,01 mg/dl.' if alt_c else 'Kreatynina w mg/dl.')
        if 'hemoglobin_g_dl' not in missing:
            if j < 20:
                alternate=j%4 in {1,2}
                val=polish_number(r['hemoglobin_g_dl']*.6206,1) if alternate else polish_number(r['hemoglobin_g_dl'],2)
            else:
                hb_val = float(r['hemoglobin_g_dl'])
                can_mmol1 = abs(round(float(f'{hb_val*0.6206:.1f}')/0.6206, 2) - hb_val) <= 0.005
                can_mmol2 = abs(round(float(f'{hb_val*0.6206:.2f}')/0.6206, 2) - hb_val) <= 0.005
                alternate = (not is_easy) and (j % 4 in {1, 2}) and (can_mmol1 or can_mmol2)
                if alternate:
                    prec = 1 if can_mmol1 else 2
                    val = polish_number(hb_val * .6206, prec)
                else:
                    val = polish_number(hb_val, 2)
            lab.append(f"Hb {val} {'mmol/l' if alternate else 'g/dl'}")
            labfields.append('hemoglobin_g_dl');conversion.append('Hb: mmol/l ÷0,6206, do 0,01 g/dl.' if alternate else 'Hb w g/dl.')
        if lab:
            add('labs',['Wyniki laboratoryjne: ','Z wydruku laboratorium: ','Badania uzupełniające: '][j%3]+'; '.join(lab)+'.',labfields,'jednostka',' '.join(conversion))
        alt_testo = (j%3==1) if not is_easy else False
        testosterone=r['testosterone_ng_dl']/28.84 if alt_testo else r['testosterone_ng_dl']
        add('labs',f"Testosteron {polish_number(testosterone,3 if alt_testo else 1)} {'nmol/l' if alt_testo else 'ng/dl'}, "+('oznaczenie w trzecim miesiącu ADT.' if r['adt'] else 'pobranie przed leczeniem, bez ADT.'))
        if 'diabetes' not in missing:
            add('comorbidity','DM t.2, leczona doustnie.' if r['diabetes'] else 'Nie stwierdzono cukrzycy.', ['diabetes'],'negacja','Udokumentowana obecność=1, jawna negacja=0; bez wywiadu=null.')
        if 'hypertension' not in missing:
            add('comorbidity','NT w wywiadzie, leczenie przewlekłe.' if r['hypertension'] else 'Nie stwierdzono nadciśnienia tętniczego.', ['hypertension'],'negacja','Wywiad, nie pojedynczy pomiar ciśnienia.')
        if 'smoking' not in missing:
            add('comorbidity',{'never':'Nigdy nie palił.','former':'Nie pali od 10 lat.','current':'Nadal pali papierosy.'}[r['smoking']],['smoking'],'negacja','Nie pali od 10 lat=former, nigdy nie palił=never, nadal pali=current.')
        if r['death']:
            add('ending',f"Dopisek do obserwacji: odnotowano zgon {display_date(r['death_date'],j)}; data późniejsza niż opisane wyniki. Przyczyny zgonu w tej kopii nie podano.")
        else:
            add('ending',['Plan: kolejne oznaczenie PSA i konsultacja urologiczna według terminu z poradni.','Zalecenia przekazano choremu; dalsze wizyty w poradni radioterapii i urologicznej.','Do kolejnej kontroli zabrać pełne wydruki badań i listę aktualnie stosowanych leków.'][j%3])
        for v in sorted(missing):
            why='Nieobecna informacja w dostarczonej kopii; nie przypisywać 0.'
            typ='brak'
            if j in {16, 53} and v=='isup_grade':
                alt_isup = 2 if r['isup_grade'] != 2 else 3
                why=f"Gleason {r['gleason_primary']}+{r['gleason_secondary']} i ISUP {alt_isup} bez rozstrzygającego aneksu. Przyjęto null, nie samodzielną korektę.";typ='sprzecznosc'
            if j in {18, 56} and v=='birth_date':
                why='Dwie daty urodzenia bez potwierdzonej korekty; PESEL nie stanowi źródła.';typ='sprzecznosc'
            if j in {17, 55}:
                why='PSA <0,01 bez wartości punktowej; PSA i Phoenix=null.';typ='oznaczalnosc'
            difficulties.append(dict(dokument=doc,zmienna=v,typ_trudnosci=typ,dlaczego_trudne=why))
        if j%6==0:
            order=['header','pathology','treatment','history','labs','comorbidity','follow','ending']; separator='\n\n'
        elif j%6==1:
            order=['header','history','comorbidity','pathology','treatment','labs','follow','ending'];separator='\n'
        elif j%6==2:
            order=['header','follow','comorbidity','history','pathology','treatment','labs','ending'];separator='\n\n'
        elif j%6==3:
            order=['header','history','treatment','labs','pathology','follow','comorbidity','ending'];separator='\n'
        elif j%6==4:
            order=['header','comorbidity','history','pathology','labs','treatment','follow','ending'];separator='\n\n'
        else:
            order=['header','labs','follow','history','pathology','treatment','comorbidity','ending'];separator='\n'
        section_names = [
            {'pathology':'ROZPOZNANIE', 'treatment':'PRZEBIEG RT', 'follow':'OBSERWACJA'},
            {'history':'Wywiad i kwalifikacja', 'follow':'Uzupełnienie z poradni po leczeniu'},
            {'follow':'1. PSA i tolerancja', 'pathology':'2. Dane rozpoznania', 'treatment':'3. Przebyte leczenie'},
            {'labs':'Załącznik laboratoryjny', 'follow':'Dopisek ambulatoryjny'},
            {'comorbidity':'Wywiad internistyczny', 'pathology':'Ocena urologiczna', 'treatment':'Leczenie — dane z karty RT'},
            {'labs':'LAB.', 'follow':'KONTROLA', 'treatment':'RT / ADT'}
        ][j % 6]
        text=separator.join((section_names[b]+'\n' if b in section_names else '')+'\n'.join(blocks[b]) for b in order if blocks[b])+'\n'
        assert 150<=len(text.split())<=400,(doc,len(text.split()))
        (folder/doc).write_text(text,encoding='utf-8')
        gold.append(dict(dokument=doc,**answer))
    csv_write(pd.DataFrame(gold,columns=['dokument']+EXTRACT),DATA/'ekstrakcja_klucz.csv')
    csv_write(pd.DataFrame(evidence),DATA/'ekstrakcja_dowody.csv')
    csv_write(pd.DataFrame(difficulties),DATA/'ekstrakcja_trudnosci.csv')
    with zipfile.ZipFile(DATA/'dokumenty.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(folder.glob('DOK-*.txt')):
            info=zipfile.ZipInfo(file.name,(2026,10,10,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o600<<16
            archive.writestr(info,file.read_bytes())
def make_readme(summary):
    counts='\n'.join(f'| {k} | {v} |' for k,v in summary['kategorie'].items())
    blocks='; '.join(f"{block}: {count}" for block,count in summary['bledy_na_bloki'].items())
    traps='\n'.join(f"- {trap['patient_id']}: {trap['uzasadnienie']}" for trap in summary['pulapki'])
    return f'''# PROSTATA-RT — dane do ćwiczeń

120 fikcyjnych mężczyzn leczonych radykalną RT ± ADT. Nie importowano danych pacjentów. Nazwiska mają człon „Fikcyjny”; wszystkie numery PESEL mają celowo błędną cyfrę kontrolną. Materiał służy ćwiczeniu higieny danych. Lokalne generowanie i testy nie stanowią oceny gotowości klinicznej ani publikacyjnej.

## Odtworzenie

W katalogu `exercises/`:

```bash
/home/linuxbrew/.linuxbrew/bin/python3 -B generator/generuj_dane.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 /home/linuxbrew/.linuxbrew/bin/python3 -B -m pytest generator/test_spojnosc.py -q -p no:cacheprovider
/home/linuxbrew/.linuxbrew/bin/python3 -B walidacja/waliduj.py dane/rejestr_brudny.xlsx
```

Generator: stały seed {SEED}, biblioteka standardowa, pandas, numpy, openpyxl. Walidator odczytuje `dane/reguly.yaml` przez PyYAML. Katalog reguł jest także skopiowany do `walidacja/reguly.yaml`. Pytest jest potrzebny do testów. Bez pobierania danych i połączeń sieciowych. Ścieżki wyników są względne wobec kodu, niezależne od katalogu uruchomienia. Wszystkie własne wyniki są nadpisywane. CSV, TXT, JSON, YAML, ZIP i XLSX są deterministyczne w użytych wersjach bibliotek; czasy ZIP/XLSX są unormowane.

## Pliki

- `dane/rejestr_czysty.csv`: 120 rekordów prawdy, 34 zmienne; BCR {summary['bcr']}/120 ({summary['bcr_procent']:.1f}%), zgony {summary['zgony']}.
- `dane/rejestr_brudny.csv` i `.xlsx`: 121 rekordów, wraz z dodatkowym duplikatem; CSV ze średnikiem, UTF-8 z BOM. Jedyna zakładka XLSX: `dane`.
- `dane/slownik_danych.csv` i `.xlsx`: nazwy, typy, jednostki, zakresy, kody braków i definicje protokołu.
- `dane/klucz_bledow.csv` i `.xlsx`: jeden wpis na zmienioną komórkę oraz jeden na dodatkowy rekord; numer wiersza Excel uwzględnia nagłówek.
- `dane/pulapki_nie_bledy.csv`: pięć prawdziwych, rzadkich wartości.
- `dane/karta_znalezisk.xlsx`: pusty formularz dla grupy.
- `dane/dokumenty/DOK-01.txt`…`DOK-60.txt` i `dane/dokumenty.zip`: 60 dokumentów dla PR-061…PR-120, 150–400 słów każdy, trzy rodzaje dokumentacji, sześć układów i odrębne narracje.
- `dane/ekstrakcja_schemat.json`: 25 pól, brak lub nierozstrzygnięta sprzeczność jako null.
- `dane/ekstrakcja_prompt.txt`: instrukcja ekstrakcji, jednostki i rozstrzyganie sprzeczności.
- `dane/ekstrakcja_klucz.csv`, `ekstrakcja_trudnosci.csv`, `ekstrakcja_dowody.csv`: standard odniesienia, trudności i dosłowne fragmenty źródła z zasadą przeliczenia.
- `dane/reguly.yaml`: id, opis, typ, zmienne, wyrażenie pandas lub zakres; kontrole wielopolowe mają parametry i identyfikator `kontrola` używany przez walidator.
- `dane/scenariusz.json`: opis i jawne definicje protokołu.
- `dane/wyniki_referencyjne/`: raport naruszeń, pokrycie klucza i podsumowanie liczbowe.
- `dane/manifest_sha256.csv`: sumy kontrolne wszystkich pozostałych plików w `dane/`.
- `generator/generuj_dane.py`, `generator/test_spojnosc.py`, `walidacja/waliduj.py`: kod i testy.
- `_archiwum_kardioonko/`: zachowany poprzedni pakiet, wraz z kodem, dokumentami i wynikami. Nie stanowi wejścia bieżącego ćwiczenia.

## Definicje i odczyt dokumentów

Gleason jest sumą wzorców. ISUP: 3+3→1, 3+4→2, 4+3→3, suma 8→4, suma 9–10→5. W uproszczonej grupie ryzyka warunki wysokiego ryzyka mają pierwszeństwo: PSA >20, ISUP 4–5, cT2c–cT4 lub cN1. Niskie: PSA <10, ISUP 1, cT1c–cT2a i cN0; pozostałe: pośrednie. To definicja ćwiczeniowa, nie pełna klasyfikacja EAU. M1 nie jest uwzględnione; v2 nie wskazuje konkretnej pułapki M1 ani kolumny M.

Phoenix: ostatnie PSA **≥ nadir + 2 ng/ml**, z granicą włączoną. SBRT ⇔ 5 frakcji. Dopuszczalne dawki i frakcje: 78/39, 76/38, 60/20, 62/20, 70/28, 36,25/5 i 40/5. Dawka dotyczy prostaty. ADT=0 wymaga zerowego czasu ADT; czas w rejestrze jest całkowitym planem, a nie czasem do oznaczenia testosteronu. Typowe czasy ADT w protokole: 6 mies. w pośrednim niekorzystnym i 18–36 mies. w wysokim ryzyku.

Kreatynina µmol/l ÷88,4 → mg/dl; Hb mmol/l ÷0,6206 → g/dl, obie do dwóch miejsc. Testosteron nmol/l ×28,84 → ng/dl. Bez jawnej jednostki nie przeliczać na podstawie samego wyniku. Zapisy dat z ukośnikiem **w dokumentach** oznaczają DD/MM/RRRR; brudny rejestr nie ma tej deklaracji. Numer seryjny Excela wymaga potwierdzenia systemu dat. Tekst „kwiecień 2025” nie podaje dnia.

Brak informacji o NT, DM lub paleniu to null. „Nie pali od 10 lat” oznacza former. CTCAE w kluczu jest maksimum całej obserwacji. Konsultacje kwalifikacyjne mają wyraźnie oddzielone późniejsze uzupełnienie wyników. W DOK-14 potwierdzona data urodzenia ma pierwszeństwo przed wiekiem ze skierowania. W DOK-16 aneks potwierdza ISUP 3 i koryguje ISUP 2. W DOK-17 sprzeczność ISUP bez aneksu daje null. W DOK-19 dwie nierozstrzygnięte daty urodzenia dają null. W DOK-18 PSA <0,01 bez wyniku punktowego i wynik Phoenix mają null. Puste pola klucza CSV odpowiadają null w JSON; PESEL nie jest źródłem danych do ekstrakcji.

## Błędy i pułapki

{summary['bledy']} błędów: 55 zmienionych komórek oraz jeden dodatkowy pełny duplikat PR-076 pod ID PR-121. Dodatkowy wiersz liczymy jako jeden błąd rekordu, nie 33 błędy poszczególnych wartości. W kluczu ma pustą wartość prawdziwą ID; po potwierdzeniu należy usunąć dodatkowy rekord. Brudnego i czystego rejestru nie łączyć wyłącznie po ID: identyfikatory zmieniono i powielono. Numer wiersza Excel przestaje być stabilny po sortowaniu pliku.

Rozmieszczenie ma stały seed {summary['seed_rozmieszczenia']}. Liczby błędów w kolejnych blokach 20 pacjentów: {blocks}. To 55 zmienionych komórek w PR-001…PR-120; dodatkowy duplikat jest wierszem 121 danych (122 w Excelu). Każdy pacjent ma najwyżej jeden wstrzyknięty błąd. Pięć pułapek leży w pięciu różnych blokach, w wierszach bez błędów. Wariant „pr 014”, źródło pełnego duplikatu PR-076 oraz prawda histopatologiczna PR-116 i PR-117 zachowują pozycje; pozostałe przykłady są losowane wraz z odpowiadającą im prawdą.

Kontrakt v2 podaje orientacyjnie 36–42, ale jego pełna lista wymaga co najmniej 56 osobnych błędów. Przyjęto pełne pokrycie: wszystkie wymienione warianty faktycznie występują w brudnym rejestrze i kluczu, co sprawdza test. Nie przeniesiono brakujących wariantów wyłącznie do testów.

| Kategoria | Liczba |
| --- | ---: |
{counts}
| Razem | {summary['bledy']} |

Pułapki (reguły i klucz nie zgłaszają tych rekordów jako błędnych):

{traps}

## Wynik walidacji i ograniczenia

Reguły: {summary['naruszenia_regul']} naruszeń, {summary['komorki_zgloszone']} różnych komórek, {summary['bledy_wykryte_regulami']}/{summary['bledy']} trafień w klucz. Jedna komórka może naruszać kilka reguł. Dodatkowo wskazane poprawne pola należą do sprzecznych par lub powtarzającego się ID; walidator nie zna prawdy i nie rozstrzyga, który element pary jest błędny. Pokrycie klucza nie oznacza takiej samej skuteczności na innych danych.

Wyrażenia agregatowe YAML pokazują przykładową kontrolę; pełny walidator stosuje `kontrola`, wszystkie `zmienne`, parametry i słownik. Aplikacja wykonująca wyłącznie wyrażenia musi uwzględnić to rozszerzenie dla pełnej zgodności. Nie testowano aplikacji z części B ani modelu językowego. Testy dokumentów odczytują jawne fakty niezależnie od generatora i sprawdzają cytowane fragmenty, przeliczenia, negacje oraz null; nie stanowią pełnego audytu medycznego. Opcjonalnej implementacji R nie przygotowano.

Do pracy grupowej udostępnić brudny rejestr, słownik, dokumenty i kartę znalezisk. Czysty rejestr, klucze i wyniki referencyjne odsłonić podczas omówienia.
'''


def generate():
    DATA.mkdir(parents=True,exist_ok=True)
    layout=make_layout()
    clean=make_clean(layout);dictionary=make_dictionary();dirty,key=make_dirty(clean,layout)
    csv_write(clean,DATA/'rejestr_czysty.csv');csv_write(dirty,DATA/'rejestr_brudny.csv',dirty=True)
    xlsx_write(dirty,DATA/'rejestr_brudny.xlsx')
    csv_write(dictionary,DATA/'slownik_danych.csv');xlsx_write(dictionary,DATA/'slownik_danych.xlsx','slownik',DICTIONARY_WIDTHS)
    csv_write(key,DATA/'klucz_bledow.csv');xlsx_write(key,DATA/'klucz_bledow.xlsx','klucz')
    traps=make_traps(clean,layout)
    csv_write(traps,DATA/'pulapki_nie_bledy.csv')
    make_documents(clean)
    (DATA/'ekstrakcja_schemat.json').write_text(json.dumps(schema_object(dictionary),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    prompt=('Wyodrębnij dane z syntetycznej dokumentacji raka gruczołu krokowego do załączonego JSON Schema. Zwróć tylko JSON, wszystkie wymagane pola. '
            'Brak informacji lub nierozstrzygnięta sprzeczność: null, nie 0. Nie zgaduj. Daty ISO; ukośnik w dokumentach oznacza DD/MM/RRRR. '
            'Kreatynina µmol/l ÷88,4 → mg/dl. Hb mmol/l ÷0,6206 → g/dl. Zaokrąglaj obie do 0,01. '
            'Gs 3+4 różni się od 4+3. Potwierdzony aneks histopatologiczny rozstrzyga ISUP; bez aneksu sprzeczne ISUP=null, nawet gdy wzorce pozwalają je wyliczyć. '
            'Grupę ryzyka przepisz z jawnej kwalifikacji; nie rozstrzygaj sprzecznych źródeł po cichu. '
            'Przepisz technikę i dawkę na prostatę, a nie na węzły. Początek RT to pierwsza frakcja, nie rozpoczęcie ADT. '
            'adt_months to jawnie podany całkowity plan leczenia, nie czas od pierwszego podania do wizyty. '
            'Phoenix=1 gdy ostatnie PSA >= nadir+2, inaczej 0; bez obu wiarygodnych pomiarów null. PSA <0,01 bez wartości punktowej=null; nie zamieniaj na zero. '
            'CTCAE: maksimum całego okresu, nie tylko objawy aktualne. Nie pali od 10 lat=former. Brak wywiadu o NT/DM nie oznacza 0. '
            'Potwierdzona data urodzenia ma pierwszeństwo przed błędnym wiekiem; bez rozstrzygnięcia między dwiema datami null. '
            'Nie odtwarzaj danych z fikcyjnego PESEL; nie zwracaj nazwiska ani PESEL.\n')
    (DATA/'ekstrakcja_prompt.txt').write_text(prompt,encoding='utf-8')
    xlsx_write(pd.DataFrame(columns=['patient_id','zmienna','problem','decyzja']),DATA/'karta_znalezisk.xlsx','znaleziska')
    scenario={'nazwa':'PROSTATA-RT','opis':'Jednoośrodkowy, w pełni syntetyczny rejestr mężczyzn z rakiem gruczołu krokowego leczonych radykalną radioterapią IMRT/VMAT lub SBRT ± ADT, z obserwacją PSA i toksyczności.','definicje':PROTOCOL,'syntetyczne':True,'wersja_kontraktu':2}
    (DATA/'scenariusz.json').write_text(json.dumps(scenario,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rules=make_rules(dictionary)
    rules_text=json.dumps(rules,ensure_ascii=False,indent=2)+'\n'
    (DATA/'reguly.yaml').write_text(rules_text,encoding='utf-8')
    (ROOT/'walidacja').mkdir(exist_ok=True)
    (ROOT/'walidacja/reguly.yaml').write_text(rules_text,encoding='utf-8')
    sys.path.insert(0,str(ROOT/'walidacja'))
    from waliduj import validate
    reference=DATA/'wyniki_referencyjne';reference.mkdir(exist_ok=True)
    report=validate(dirty,dictionary)
    csv_write(report,reference/'walidacja_reguly_raport.csv')
    hits=set(zip(report.wiersz_excel.astype(int),report.zmienna))
    coverage=key[['error_id','wiersz_excel','patient_id_w_pliku','zmienna','wykrywalne_regula']].copy()
    coverage['wykryty']=[int((int(e.wiersz_excel),e.zmienna) in hits) for e in key.itertuples()]
    csv_write(coverage,reference/'pokrycie_klucza.csv')
    keyed=set(zip(key.wiersz_excel.astype(int),key.zmienna))
    block_counts=Counter((key.loc[key.wiersz_excel<=121,'wiersz_excel']-2)//20)
    summary={'scenariusz':'PROSTATA-RT','seed':SEED,'seed_rozmieszczenia':LAYOUT_SEED,
             'bledy_na_bloki':{f'{b*20+1}–{(b+1)*20}':block_counts[b] for b in range(6)},'pulapki':traps.to_dict('records'),
             'rekordy_czyste':len(clean),'rekordy_brudne':len(dirty),'zmienne':len(COLUMNS),
             'bledy':len(key),'kategorie':dict(sorted(Counter(key.kategoria).items())),'bcr':int(clean.bcr_phoenix.sum()),'bcr_procent':float(clean.bcr_phoenix.mean()*100),
             'zgony':int(clean.death.sum()),'dokumenty':60,'naruszenia_regul':len(report),'komorki_zgloszone':len(hits),
             'bledy_wykryte_regulami':int(coverage.wykryty.sum()),'dodatkowe_komorki_do_wyjasnienia':[{'wiersz_excel':int(r),'zmienna':v} for r,v in sorted(hits-keyed)]}
    (reference/'podsumowanie.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    readme=make_readme(summary)
    (ROOT/'README_dane.md').write_text(readme,encoding='utf-8')
    (DATA/'README_dane.md').write_text(readme,encoding='utf-8')
    manifest=[]
    for path in sorted(DATA.rglob('*')):
        if path.is_file() and path.name!='manifest_sha256.csv':
            manifest.append(dict(plik=path.relative_to(DATA).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bajty=path.stat().st_size))
    csv_write(pd.DataFrame(manifest),DATA/'manifest_sha256.csv')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':
    generate()
