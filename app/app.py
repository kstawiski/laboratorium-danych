"""Laboratorium danych — aplikacja dla syntetycznych pakietów ćwiczeniowych."""
from io import StringIO
import hashlib
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from lab.config import APP_DIR, data_dir, model_configs
from lab.data import (read_table, dictionary, excel_bytes, csv_bytes, document_zip,
                      extraction_schema, extraction_prompt, FINDING_COLUMNS, package_problem,
                      scenario, registry_file, conversion_factors)
from lab.analysis import describe, missing_codes, numeric_series, outliers, eda_payload, normalize_id
from lab.rules import Rule, package_rules, run_rules, validate_rule, RESULT_COLUMNS
from lab.scoring import compare_findings, compare_extraction, restrict_to_rows, split_kept, pair_set
from lab.llm import call_model, ModelError
from lab.prompts import TEXT_SCHEMA, RULE_SCHEMA, rule_messages, DEFAULT_CLINICAL_ROWS
from lab.jobs import extraction_job, clinical_jobs

def _arrow_safe(data):
    """Kolumny tekstowo-liczbowe (np. 'brak' obok liczb) pokazujemy jako tekst, żeby pyarrow nie zgłaszał błędu."""
    if isinstance(data, pd.DataFrame):
        data = data.copy()
        for column in data.columns:
            if data[column].dtype == object:
                data[column] = data[column].map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))
    return data


def show_df(data, **kwargs):
    return st.dataframe(_arrow_safe(data), **kwargs)


st.set_page_config(page_title="Laboratorium danych", page_icon="🔬", layout="wide")
st.markdown("""<style>.stApp {background:#fff} .block-container {padding-top:2rem}
[data-testid='stMetricValue'] {font-size:1.7rem} h1 {font-size:2rem}
</style>""", unsafe_allow_html=True)
st.title("Laboratorium danych")
st.warning("Dane są w pełni syntetyczne. Nie wolno tu wklejać ani wgrywać prawdziwych danych pacjentów.")

try:
    configs = model_configs()
except (OSError, ValueError):
    st.error("Nie można odczytać konfiguracji modelu. Sprawdź zmienne środowiskowe i plik klucza.")
    st.stop()
with st.sidebar:
    st.header("Ustawienia")
    group = st.text_input("Nazwa grupy", key="group", placeholder="np. Grupa 1", max_chars=80)
    chosen_model = st.selectbox("Model", list(configs), key="chosen_model")
    temperature = st.slider("Temperatura", 0.0, 1.0, 0.2, 0.05, key="temperature")
    bypass_cache = st.checkbox("Nie używaj pamięci podręcznej (nowe zapytanie do modelu)", key="bypass_cache")
    st.caption(f"{configs[chosen_model].model} · limit czasu 180 s · {configs[chosen_model].concurrency} zapytań naraz")
    uploaded = st.file_uploader("Własny rejestr (xlsx / csv)", type=["xlsx", "csv"], key="registry_upload")
    st.caption("Wgrywaj wyłącznie dane syntetyczne. Model zapasowy wybierz ręcznie, gdy serwer jest zajęty.")

path = data_dir()
problem = package_problem(path)
if problem:
    path = APP_DIR / "tests" / "fixtures"
    st.warning(problem + " Używany jest mały syntetyczny zestaw próbny (fixture).")
st.sidebar.caption(f"Katalog danych: {path}")
try:
    definitions = dictionary(path)
    metadata = scenario(path)
    source = registry_file(path)
    frame = read_table(uploaded, uploaded.name) if uploaded is not None else read_table(source)
    if frame.empty:
        raise ValueError("Plik nie zawiera wierszy danych.")
    if len(frame) > 10000:
        raise ValueError("Zestaw ćwiczeniowy może mieć najwyżej 10 000 wierszy.")
except (OSError, ValueError, StopIteration, UnicodeError) as exc:
    st.error(f"Nie można wczytać danych: {exc}")
    st.stop()

st.caption(f"{metadata['nazwa']} · Przygotowanie i higiena danych · UM w Łodzi")

signature = hashlib.sha256((str(path) + json.dumps(metadata, ensure_ascii=False) + frame.to_json(orient="split", default_handler=str) + definitions.to_json(orient="split")).encode()).hexdigest()
if st.session_state.get("data_signature") != signature:
    for key in ("rule_results", "clinical_results", "clinical_failures", "extraction_results", "extraction_failures", "eda_comment", "custom_rules", "proposed_rules", "group_findings", "key_shown", "extraction_prompt", "selected_docs", "model_feedback"):
        st.session_state.pop(key, None)
    st.session_state.data_signature = signature
specs = definitions.set_index("zmienna").to_dict("index")


def ask(messages, schema, tab, max_tokens=700):
    queued = st.empty()
    try:
        with st.spinner("Model analizuje dane…"):
            result = call_model(configs[chosen_model], messages, schema, temperature=temperature,
                                bypass_cache=bypass_cache, group=group, tab=tab, max_tokens=max_tokens,
                                score_extraction=tab == "AI: ekstrakcja z dokumentów",
                                on_queue=lambda: queued.info("Zapytanie czeka w kolejce. Serwer obsługuje inne grupy."))
        queued.empty()
        feedback = f"{configs[chosen_model].model} · {result.elapsed:.1f} s · {'pamięć podręczna' if result.cached else 'nowa odpowiedź modelu'}"
        st.session_state.model_feedback = feedback
        st.caption(feedback)
        return result.value
    except ModelError as exc:
        queued.empty()
        st.error(str(exc))
        return None


def ask_job(job):
    return ask(job.messages, job.schema, job.tab, job.max_tokens)


def download_table(frame, filename, key):
    st.download_button("Pobierz CSV", csv_bytes(frame), filename, "text/csv", key=key)


def optional_table(name):
    file = path / name
    return read_table(file) if file.exists() else pd.DataFrame()


def ensure_findings(table):
    if not {"patient_id", "zmienna"}.issubset(table):
        raise ValueError("Karta musi zawierać patient_id i zmienna.")
    table = table.copy()
    for column in FINDING_COLUMNS:
        if column not in table:
            table[column] = ""
    return table[FINDING_COLUMNS]


tabs = st.tabs(["Start", "EDA", "Reguły walidacyjne", "AI: ekstrakcja z dokumentów",
                "AI: wiarygodność kliniczna", "Porównanie z kluczem", "Czat z modelem"])

with tabs[0]:
    st.caption("1. Wpisz nazwę grupy. 2. Przeczytaj protokół. 3. Pobierz materiały.")
    st.header(metadata["nazwa"])
    st.write(metadata.get("opis", ""))
    st.subheader("Cel zajęć")
    st.write("Rozpoznaj problemy w rejestrze, zapisz decyzję i porównaj wyniki reguł, AI oraz własnej oceny. Nie poprawiaj wartości bez uzasadnienia w źródle.")

    st.write("Nazwa grupy jest zapamiętana w tej sesji. Wpisz ją w panelu po lewej.")
    st.subheader("Materiały do pobrania")
    for label, name, mime in [
        ("Brudny rejestr · Excel", "rejestr_brudny.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("Brudny rejestr · CSV", "rejestr_brudny.csv", "text/csv"),
        ("Słownik danych · Excel", "slownik_danych.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("Słownik danych · CSV", "slownik_danych.csv", "text/csv"),
    ]:
        file = path / name
        if file.exists():
            st.download_button(label, file.read_bytes(), name, mime, key=f"download:{name}")
    st.download_button("Karta znalezisk · Excel", excel_bytes(pd.DataFrame(columns=FINDING_COLUMNS), "znaleziska"), "karta_znalezisk.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="download_card")
    if (path / "dokumenty").exists():
        st.download_button("Dokumenty syntetyczne · ZIP", document_zip(path), "dokumenty.zip", "application/zip", key="download_docs")
    st.subheader("Definicje protokołu ćwiczeniowego")
    protocol = metadata.get("definicje", {})
    if isinstance(protocol, dict):
        for label, definition in protocol.items():
            st.write(f"**{label}:** {definition}")
    else:
        st.write(protocol)

with tabs[1]:
    st.caption("1. Wybierz zmienną. 2. Sprawdź braki i rozkład. 3. Zapisz wartości wymagające wyjaśnienia.")
    st.header("Poznaj dane przed analizą")
    st.write(f"Rejestr: {len(frame)} wierszy, {len(frame.columns)} kolumn. Własny plik wybierz w panelu po lewej.")
    show_df(describe(frame, definitions), hide_index=True, width="stretch")
    variable = st.selectbox("Zmienna do obejrzenia", list(frame.columns), key="eda_variable")
    spec = specs.get(variable, {})
    st.caption(spec.get("etykieta", variable))
    codes = missing_codes(spec.get("kod_braku"))
    if spec.get("typ") in {"kategoria", "logiczna"}:
        counts = frame[variable].map(str).value_counts(dropna=False).rename_axis("wartość").reset_index(name="liczność")
        show_df(counts, hide_index=True, width="stretch")
    if spec.get("typ") in {"liczba", "liczba_calkowita"}:
        nums = numeric_series(frame[variable], codes)
        chart_data = pd.DataFrame({variable: nums.dropna()})
        if not chart_data.empty:
            left, right = st.columns(2)
            with left: st.plotly_chart(px.histogram(chart_data, x=variable, title="Rozkład wartości", template="plotly_white"), width="stretch")
            with right: st.plotly_chart(px.box(chart_data, y=variable, title="Wykres pudełkowy", template="plotly_white"), width="stretch")
        st.caption("Na wykresach pomijamy kody braków i niejednoznaczne liczby. IQR wskazuje wartości do obejrzenia; sam nie dowodzi błędu. Dane źródłowe nie są zmieniane.")
        flagged = outliers(frame, variable, spec)
        show_df(flagged, hide_index=True, width="stretch")
        if st.button("Poproś AI o komentarz kliniczny do wartości odstających", key="eda_ai"):
            payload = eda_payload(frame, variable, spec)
            answer = ask([{"role": "system", "content": "Skomentuj statystyki i wartości odstające w syntetycznym rejestrze. Rozróżnij wartość niemożliwą od rzadkiej, możliwej. Nie diagnozuj. JSON z polem odpowiedz."},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], TEXT_SCHEMA, "EDA")
            if answer is not None:
                st.session_state.eda_comment = {"variable": variable, "answer": answer["odpowiedz"]}
        comment = st.session_state.get("eda_comment", {})
        if comment.get("variable") == variable:
            st.write(comment["answer"])
    with st.expander("Wiersze źródłowe (numery jak w Excelu, nagłówek = 1)"):
        show_df(frame.assign(wiersz=frame.index + 2), hide_index=True, width="stretch")

with tabs[2]:
    st.caption("1. Wybierz reguły. 2. Uruchom kontrolę. 3. Przejrzyj naruszenia i zapisz decyzje.")
    st.header("Reguły walidacyjne")
    ready_rules, rule_notes = package_rules(path, definitions)
    for note in rule_notes:
        st.warning(note)
    st.caption("Reguły pochodzą z pakietu danych. Naruszenie wymaga sprawdzenia źródła przed korektą.")
    all_rules = ready_rules + st.session_state.get("custom_rules", [])
    selected_rules = []
    for category in ("zakres", "format", "spójność", "czas", "unikalność"):
        subset = [r for r in all_rules if r.category == category]
        with st.expander(f"{category.capitalize()} · {len(subset)} reguł"):
            for rule in subset:
                if st.checkbox(rule.description, value=True, key=f"rule:{rule.id}"):
                    selected_rules.append(rule)
    with st.form("custom_rule_form"):
        st.subheader("Dodaj własną regułę")
        mode = st.radio("Rodzaj", ["Zakres", "Wyrażenie pandas query"], horizontal=True, key="custom_mode")
        custom_variable = st.selectbox("Zmienna reguły", list(frame.columns), key="custom_variable")
        a, b = st.columns(2)
        minimum = a.text_input("Minimum (puste = bez granicy)", key="custom_min")
        maximum = b.text_input("Maksimum (puste = bez granicy)", key="custom_max")
        expression = st.text_input("Warunek naruszenia", placeholder=f"{next((n for n in frame if specs.get(n, {}).get('typ') == 'liczba'), frame.columns[0])} < 0", key="custom_expression")
        st.caption("Wpisz warunek naruszenia z nazwami kolumn. Dozwolone: porównania, and/or/not i + - * /. Bez funkcji i metod.")
        submit = st.form_submit_button("Dodaj regułę", key="custom_add")
    if submit:
        try:
            for bound in (minimum, maximum):
                if bound.strip():
                    float(bound.replace(",", "."))
            raw = {"id": f"custom:{len(st.session_state.get('custom_rules', []))}", "kind": "range" if mode == "Zakres" else "query",
                   "description": f"Własna: {custom_variable} [{minimum}; {maximum}]" if mode == "Zakres" else f"Własna: {expression}",
                   "variable": custom_variable, "minimum": minimum, "maximum": maximum, "expression": expression}
            new_rule = validate_rule(raw, set(frame.columns))
            # Sprawdzamy także typy rzeczywistych kolumn, zanim reguła trafi na listę.
            run_rules(frame, definitions, [new_rule])
            st.session_state.setdefault("custom_rules", []).append(new_rule)
            st.rerun()
        except ValueError as exc:
            st.error(f"Nie dodano reguły: {exc}")
    if st.button("Uruchom wybrane reguły", key="rules_run"):
        try:
            st.session_state.rule_results = run_rules(frame, definitions, selected_rules)
        except ValueError as exc:
            st.error(f"Nie można uruchomić reguł: {exc}")
    if "rule_results" in st.session_state:
        st.write(f"Naruszenia: {len(st.session_state.rule_results)}")
        show_df(st.session_state.rule_results, hide_index=True, width="stretch")
        download_table(st.session_state.rule_results, "naruszenia_regul.csv", "rules_download")
    if st.button("AI: zaproponuj reguły na podstawie słownika", key="rules_ai"):
        answer = ask(rule_messages(definitions), RULE_SCHEMA, "Reguły walidacyjne")
        if answer is not None:
            st.session_state.proposed_rules = answer["reguly"]
    proposals = st.session_state.get("proposed_rules", [])
    if proposals:
        st.subheader("Przejrzyj propozycje AI")
        show_df(pd.DataFrame(proposals), hide_index=True, width="stretch")
        accepted = st.multiselect("Reguły do dodania po przejrzeniu", list(range(len(proposals))), format_func=lambda i: proposals[i]["description"], key="accepted_rules")
        if st.button("Dodaj przejrzane reguły AI", key="rules_accept"):
            valid, errors = [], []
            for i in accepted:
                try:
                    raw = dict(proposals[i], id=f"ai:{len(st.session_state.get('custom_rules', [])) + len(valid)}")
                    rule = validate_rule(raw, set(frame.columns))
                    run_rules(frame, definitions, [rule])
                    valid.append(rule)
                except ValueError as exc:
                    errors.append(f"{proposals[i]['description']}: {exc}")
            st.session_state.setdefault("custom_rules", []).extend(valid)
            if errors:
                for error in errors: st.error(error)
            if valid:
                st.success(f"Dodano {len(valid)} reguł. Pojawią się na liście po następnym działaniu.")

with tabs[3]:
    st.caption("1. Wybierz dokumenty. 2. Przejrzyj lub zmień polecenie. 3. Uruchom ekstrakcję i porównaj pola z kluczem.")
    st.header("Ekstrakcja z dokumentów")
    documents = sorted(file.name for file in (path / "dokumenty").glob("DOK-*.txt"))
    if not documents or not (path / "ekstrakcja_schemat.json").exists():
        st.info("Dokumenty lub schemat nie są jeszcze dostępne w DATA_DIR.")
    else:
        try:
            schema = extraction_schema(path)
            fields = list(schema["properties"])
            selected_docs = st.multiselect("Dokumenty", documents, default=documents[:1], key="selected_docs")
            if selected_docs:
                preview = st.selectbox("Podgląd dokumentu", selected_docs, key="preview_doc")
                st.text_area("Dokument syntetyczny", (path / "dokumenty" / preview).read_text(encoding="utf-8"), height=220, disabled=True, key=f"doc_preview_text:{preview}")
            prompt = st.text_area("Polecenie ekstrakcji (możesz edytować)", extraction_prompt(path), height=200, key="extraction_prompt")
            st.button("Przywróć domyślne polecenie", key="extraction_prompt_reset",
                      on_click=lambda: st.session_state.update(extraction_prompt=extraction_prompt(path)))
            all_selected = st.checkbox("Wszystkie wybrane dokumenty", value=True, key="extract_all")
            if st.button("Uruchom ekstrakcję", disabled=not selected_docs, key="extraction_run"):
                results, failures = {}, []
                progress = st.progress(0.0)
                jobs = selected_docs if all_selected else [preview]
                for i, name in enumerate(jobs):
                    text = (path / "dokumenty" / name).read_text(encoding="utf-8")
                    answer = ask_job(extraction_job(name, text, prompt, schema))
                    if answer is not None:
                        results[name] = answer
                    else:
                        failures.append(name)
                    progress.progress((i + 1) / len(jobs))
                st.session_state.extraction_results = results
                st.session_state.extraction_failures = failures
            results = st.session_state.get("extraction_results", {})
            failures = st.session_state.get("extraction_failures", [])
            if failures:
                st.warning("Brak wyniku ekstrakcji: " + ", ".join(failures) + ". Te dokumenty nie są uwzględnione w dokładności.")
            if results:
                output = pd.DataFrame([{"dokument": document, **result} for document, result in results.items()])
                show_df(output, hide_index=True, width="stretch")
                download_table(output, "ekstrakcja_ai.csv", "extract_download")
                gold = optional_table("ekstrakcja_klucz.csv")
                if not gold.empty:
                    comparisons, per_doc, accuracy = compare_extraction(results, gold, fields, conversion_factors(definitions))
                    st.metric("Dokładność ogółem (zgodne pola / ocenione pola)", f"{accuracy:.1f}%" if accuracy is not None else "brak klucza")
                    show_df(per_doc, hide_index=True, width="stretch")
                    st.caption("Zielony = zgodne, czerwony = rozbieżność. Porównanie liczb: tolerancja bezwzględna 0,02; względna 0,01%. Brak oznacza null.")
                    st.caption("Odpowiedzi z błędną kategorią, datą lub zakresem są zachowane do oceny rozbieżności, jeśli struktura i typy JSON są poprawne.")
                    display = comparisons.copy()
                    for column in ("wynik AI", "klucz"):
                        display[column] = display[column].map(lambda v: "null" if v is None or pd.isna(v) else str(v))
                    style = _arrow_safe(display).style.apply(lambda row: ["background-color: #dcfce7" if row["zgodność"] else "background-color: #fee2e2"] * len(row), axis=1)
                    st.dataframe(style, hide_index=True, width="stretch")
                    st.subheader("Rozbieżności")
                    show_df(display[~display["zgodność"]], hide_index=True, width="stretch")
                    download_table(comparisons, "porownanie_ekstrakcji.csv", "extract_compare_download")
                else:
                    st.info("Klucz ekstrakcji nie jest jeszcze dostępny.")
        except (OSError, ValueError, KeyError) as exc:
            st.error(f"Nie można odczytać materiałów ekstrakcji: {exc}")

with tabs[4]:
    st.caption("1. Wybierz zakres. 2. Uruchom ocenę. 3. Sprawdź podejrzenia w słowniku i źródle.")
    st.header("Wiarygodność kliniczna")
    st.write("Model ocenia dane w paczkach po 10 wierszy. Wybierz zakres dla swojej grupy.")
    a, b = st.columns(2)
    first = a.number_input("Pierwszy rekord (1 = pierwszy wiersz danych)", 1, len(frame), 1, key="clinical_first")
    last = b.number_input("Ostatni rekord", 1, len(frame), min(DEFAULT_CLINICAL_ROWS, len(frame)), key="clinical_last")
    include_notes = st.checkbox("Dołącz notes do analizy AI", key="include_notes")
    if include_notes:
        st.warning("Notes może zawierać identyfikatory. W tym ćwiczeniu używaj wyłącznie danych syntetycznych.")
    if st.button("Oceń wybrane wiersze", key="clinical_run"):
        if first > last:
            st.error("Pierwszy rekord musi poprzedzać ostatni.")
        else:
            jobs = list(clinical_jobs(frame, definitions, metadata, int(first), int(last), include_notes))
            findings, failed = [], []
            progress = st.progress(0.0)
            total = len(jobs)
            for i, job in enumerate(jobs):
                batch = frame.iloc[int(first)-1+i*10:min(int(last), int(first)-1+(i+1)*10)]
                answer = ask_job(job)
                if answer is not None:
                    batch_ids = set(batch["patient_id"].map(normalize_id)) if "patient_id" in batch else set()
                    for item in answer["podejrzenia"]:
                        if item["zmienna"] not in frame or normalize_id(item["patient_id"]) not in batch_ids:
                            failed.append(f"AI zgłosiło ID lub zmienną spoza paczki: {item['patient_id']} / {item['zmienna']}. Zgłoszenie zachowano do oceny fałszywych alarmów.")
                        findings.append(item)
                else:
                    failed.append(f"Brak odpowiedzi dla paczki {i+1}.")
                progress.progress((i+1)/total)
            st.session_state.clinical_results = pd.DataFrame(findings, columns=["patient_id", "zmienna", "wartosc", "problem", "powaga", "sugerowane_dzialanie"])
            st.session_state.clinical_failures = failed
            st.session_state.clinical_range = (int(first), int(last))
    for failure in st.session_state.get("clinical_failures", []): st.warning(failure)
    if "clinical_results" in st.session_state:
        show_df(st.session_state.clinical_results, hide_index=True, width="stretch")
        download_table(st.session_state.clinical_results, "podejrzenia_ai.csv", "clinical_download")

with tabs[5]:
    st.caption("1. Wczytaj kartę grupy. 2. Zakończ własną ocenę. 3. Kliknij „Pokaż klucz” i porównaj wyniki.")
    st.header("Porównanie z kluczem")
    st.write("Wczytaj kartę znalezisk grupy lub wklej tabelę z nagłówkiem patient_id, zmienna, problem, decyzja. CSV może mieć separator średnik; tabela z Excela — tabulator.")
    findings_upload = st.file_uploader("Karta znalezisk grupy", type=["xlsx", "csv"], key="findings_upload")
    pasted = st.text_area("Wklej kartę znalezisk", key="findings_paste", height=120)
    if st.button("Wczytaj znaleziska grupy", key="findings_load"):
        try:
            if findings_upload is not None:
                findings = read_table(findings_upload, findings_upload.name)
            elif pasted.strip():
                findings = read_table(StringIO(pasted), "znaleziska.csv")
            else:
                raise ValueError("Wybierz plik albo wklej tabelę.")
            st.session_state.group_findings = ensure_findings(findings)
            st.success(f"Wczytano {len(findings)} zgłoszeń.")
        except (ValueError, OSError, UnicodeError) as exc:
            st.error(f"Nie można wczytać karty: {exc}")
    if "group_findings" in st.session_state:
        show_df(st.session_state.group_findings, hide_index=True, width="stretch")
    st.warning("Pokaż klucz dopiero po zakończeniu własnej oceny. Kliknięcie odsłoni rozwiązanie ćwiczenia.")
    if st.button("Pokaż klucz", key="key_reveal"):
        st.session_state.key_shown = True
    if st.session_state.get("key_shown"):
        try:
            key = optional_table("klucz_bledow.csv")
            if key.empty:
                st.info("Klucz błędów nie jest jeszcze dostępny.")
            else:
                group = st.session_state.get("group_findings", pd.DataFrame(columns=FINDING_COLUMNS))
                group_flags, group_kept = split_kept(group)
                sources = {"Reguły": st.session_state.get("rule_results", pd.DataFrame(columns=RESULT_COLUMNS)),
                           "AI": st.session_state.get("clinical_results", pd.DataFrame(columns=["patient_id", "zmienna"])),
                           "Grupa": group_flags}
                traps = optional_table("pulapki_nie_bledy.csv")
                ai_range = st.session_state.get("clinical_range")
                default = ai_range or (1, len(frame))
                st.write("Zakres porównania: te same wiersze dla klucza, reguł, AI i grupy. Domyślnie to zakres, który grupa oceniła w zakładce AI.")
                c1, c2 = st.columns(2)
                first = int(c1.number_input("Porównaj od wiersza", 1, len(frame), default[0], key=f"compare_first:{default}"))
                last = int(c2.number_input("do wiersza", 1, len(frame), default[1], key=f"compare_last:{default}"))
                if first > last:
                    first, last = last, first
                key_in, sources_in, traps_in = restrict_to_rows(key, sources, traps, frame, first, last)
                metrics, caught, false = compare_findings(key_in, sources_in, traps_in)
                show_df(metrics, hide_index=True, width="stretch")
                st.caption(f"Wiersze {first}–{last}: {len(key_in)} błędów z klucza. Dopasowanie: znormalizowany patient_id + pojedyncza zmienna. Powtórzone zgłoszenia tej samej pary liczymy raz. Czułość: wykryte wpisy klucza / wpisy klucza w zakresie; precyzja: trafne pary / zgłoszone pary. Brak zgłoszeń = precyzja nieokreślona.")
                if ai_range is None:
                    st.caption("AI nie oceniało jeszcze wierszy w tej sesji, więc jego wynik jest pusty.")
                elif (first, last) != ai_range:
                    st.warning(f"AI oceniało tylko wiersze {ai_range[0]}–{ai_range[1]}. Poza tym zakresem jego wynik nie jest porównywalny z regułami i grupą.")
                st.caption("Duplikat ID może dopasować więcej niż jeden wpis klucza; ten wynik nie rozstrzyga, którego wiersza dotyczy zgłoszenie. Kontrola duplikatów wymaga całego rejestru (wiersze 1–" + str(len(frame)) + ").")
                if not group_kept.empty:
                    kept = restrict_to_rows(key, {"Grupa": group_kept}, traps, frame, first, last)[1]["Grupa"]
                    trap_pairs = pair_set(traps_in) if traps_in is not None and not traps_in.empty else set()
                    key_pairs = pair_set(key_in) if not key_in.empty else set()
                    rows = []
                    for identifier, variable in sorted(pair_set(kept)):
                        verdict = ("poprawnie: rzadka, ale prawdziwa wartość" if (identifier, variable) in trap_pairs
                                   else "błąd: to wpis z klucza błędów" if (identifier, variable) in key_pairs
                                   else "brak w kluczu (wartość poprawna)")
                        rows.append({"patient_id": identifier, "zmienna": variable, "ocena decyzji „pozostaw bez zmiany”": verdict})
                    st.subheader("Wartości pozostawione bez zmiany")
                    st.caption("Te wpisy karty nie są liczone jako zgłoszenia błędów.")
                    show_df(pd.DataFrame(rows, columns=["patient_id", "zmienna", "ocena decyzji „pozostaw bez zmiany”"]), hide_index=True, width="stretch")
                chart = metrics.melt(id_vars=["źródło"], value_vars=["czułość %", "precyzja %"], var_name="miara", value_name="%")
                st.plotly_chart(px.bar(chart, x="źródło", y="%", color="miara", barmode="group", range_y=[0,100], template="plotly_white"), width="stretch")
                st.subheader("Co złapał kto")
                show_df(caught, hide_index=True, width="stretch")
                st.subheader("Fałszywe alarmy")
                show_df(false, hide_index=True, width="stretch")
                st.subheader("Klucz błędów")
                show_df(key, hide_index=True, width="stretch")
                download_table(caught, "co_zlapal_kto.csv", "comparison_download")
                if uploaded is not None:
                    st.info("Używasz własnego rejestru. Porównanie ma sens, jeśli odpowiada on pakietowi i temu kluczowi.")
        except (ValueError, OSError) as exc:
            st.error(f"Nie można porównać z kluczem: {exc}")

with tabs[6]:
    st.caption("1. Wpisz pytanie o pracę z danymi. 2. Przejrzyj odpowiedź. 3. Sprawdź proponowaną formułę lub regułę.")
    st.header("Czat z modelem")
    st.info("Nie wklejaj danych pacjentów. Pytaj o formuły Excela, reguły i pracę z danymi syntetycznymi.")
    history = st.session_state.setdefault("chat_history", [])
    if st.button("Wyczyść rozmowę", key="chat_clear"):
        st.session_state.chat_history = []
        st.rerun()
    for message in history:
        with st.chat_message(message["role"]): st.write(message["content"])
    question = st.chat_input("Np. napisz formułę Excela, która wykrywa duplikaty ID", key="chat_question")
    if question:
        if len(question) > 8000:
            st.error("Pytanie może mieć najwyżej 8000 znaków.")
        else:
            answer = ask([{"role": "system", "content": "Pomagasz lekarzom w higienie danych. Pisz po polsku. Nie proś o dane pacjentów. Zwracaj JSON z polem odpowiedz."}] + history[-12:] + [{"role": "user", "content": question}], TEXT_SCHEMA, "Czat z modelem")
            if answer is not None:
                history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer["odpowiedz"]}])
                st.rerun()

if st.session_state.get("model_feedback"):
    st.sidebar.caption("Ostatnie zapytanie: " + st.session_state.model_feedback)
