from __future__ import annotations
import math
import pandas as pd
from .analysis import normalize_id, is_missing, numeric_value


def pair_set(frame: pd.DataFrame) -> set[tuple[str, str]]:
    if frame.empty:
        return set()
    id_col = "patient_id" if "patient_id" in frame else "patient_id_w_pliku"
    if id_col not in frame or "zmienna" not in frame:
        raise ValueError("Zgłoszenia muszą zawierać kolumny patient_id i zmienna.")
    return {(normalize_id(row[id_col]), str(row["zmienna"]).strip()) for _, row in frame.iterrows()}


def compare_findings(key: pd.DataFrame, sources: dict[str, pd.DataFrame], traps: pd.DataFrame | None = None):
    targets = pair_set(key)
    trap_pairs = pair_set(traps) if traps is not None and not traps.empty else set()
    detail = key.copy()
    id_col = "patient_id_w_pliku" if "patient_id_w_pliku" in key else "patient_id"
    key_pairs = [(normalize_id(row[id_col]), str(row.zmienna).strip()) for _, row in key.iterrows()]
    metrics, false_alarms = [], []
    for label, frame in sources.items():
        findings = pair_set(frame)
        matched, false = findings & targets, findings - targets
        detected = sum(pair in findings for pair in key_pairs)
        detail[label] = [pair in findings for pair in key_pairs]
        precision = len(matched) / len(findings) if findings else None
        recall = detected / len(key) if len(key) else None
        metrics.append({"źródło": label, "wykryte": detected, "wszystkie błędy": len(key),
                        "fałszywe alarmy": len(false), "trafienia w pułapki": len(false & trap_pairs),
                        "czułość %": None if recall is None else 100 * recall,
                        "precyzja %": None if precision is None else 100 * precision})
        for identifier, variable in sorted(false):
            false_alarms.append({"źródło": label, "patient_id": identifier, "zmienna": variable, "pułapka (poprawna wartość)": (identifier, variable) in trap_pairs})
    return pd.DataFrame(metrics), detail, pd.DataFrame(false_alarms, columns=["źródło", "patient_id", "zmienna", "pułapka (poprawna wartość)"])


def keep_decision(value) -> bool:
    """Decyzja „pozostaw bez zmiany”: grupa sprawdziła wartość i uznała ją za poprawną."""
    text = str(value or "").strip().lower().replace("_", " ")
    return text.startswith("pozostaw") or text.startswith("bez zmian")


def split_kept(findings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Zgłoszenia błędów oraz wartości pozostawione bez zmiany (te nie są alarmem)."""
    if findings.empty or "decyzja" not in findings:
        return findings, findings.iloc[0:0]
    mask = findings["decyzja"].map(keep_decision)
    return findings[~mask], findings[mask]


def restrict_to_rows(key: pd.DataFrame, sources: dict[str, pd.DataFrame], traps: pd.DataFrame | None,
                     registry: pd.DataFrame, first: int, last: int):
    """Klucz, pułapki i zgłoszenia tylko dla wierszy danych first..last (1 = pierwszy wiersz danych).

    Klucz i pułapki mają numer wiersza Excela (nagłówek = wiersz 1). Zgłoszenia mają tylko
    patient_id, więc należą do zakresu, gdy ten identyfikator występuje w wybranych wierszach.
    """
    if "patient_id" not in registry:
        return key, sources, traps
    ids = {normalize_id(v) for v in registry.iloc[first - 1:last]["patient_id"]}

    def by_row(table):
        if table is None or table.empty or "wiersz_excel" not in table:
            return table
        row = pd.to_numeric(table["wiersz_excel"], errors="coerce") - 1
        return table[(row >= first) & (row <= last)]

    def by_id(table):
        if table.empty:
            return table
        id_col = "patient_id" if "patient_id" in table else "patient_id_w_pliku"
        return table[table[id_col].map(lambda v: normalize_id(v) in ids)]

    return by_row(key), {label: by_id(frame) for label, frame in sources.items()}, by_row(traps)


def null_value(value) -> bool:
    return is_missing(value, {"", "null", "nan", "none"})


def equivalent(actual, expected, variable: str) -> bool:
    if null_value(actual) or null_value(expected):
        return null_value(actual) and null_value(expected)
    if variable == "patient_id":
        return normalize_id(actual) == normalize_id(expected)
    a, b = numeric_value(actual, set()), numeric_value(expected, set())
    if not math.isnan(a) and not math.isnan(b):
        return math.isclose(a, b, abs_tol=0.02, rel_tol=1e-4)
    return str(actual).strip() == str(expected).strip()


def discrepancy(actual, expected, variable: str, factors=None) -> str:
    if null_value(actual): return "pominięcie"
    if null_value(expected): return "halucynacja"
    for factor in (factors or {}).get(variable, []):
        a, b = numeric_value(actual, set()), numeric_value(expected, set())
        if factor and not math.isnan(a) and not math.isnan(b) and (math.isclose(a / factor, b, abs_tol=0.02, rel_tol=.01) or math.isclose(a * factor, b, abs_tol=0.02, rel_tol=.01)):
            return "błąd jednostki"
    return "błędna wartość"


def compare_extraction(results: dict[str, dict], gold: pd.DataFrame, fields: list[str], factors=None):
    document_column = next((c for c in ("dokument", "document", "document_id", "plik") if c in gold), None)
    if document_column is None:
        raise ValueError("Klucz ekstrakcji musi zawierać kolumnę dokument.")
    lookup = {str(row[document_column]).removesuffix(".txt"): row for _, row in gold.iterrows()}
    rows, documents = [], []
    for document, result in results.items():
        expected = lookup.get(document.removesuffix(".txt"))
        if expected is None:
            documents.append({"dokument": document, "zgodne": 0, "pola": 0, "dokładność %": None, "uwaga": "Brak dokumentu w kluczu"})
            continue
        correct = 0
        for variable in fields:
            if variable not in expected:
                raise ValueError(f"W kluczu ekstrakcji brakuje pola {variable}.")
            actual, target = result.get(variable), expected[variable]
            ok = equivalent(actual, target, variable)
            correct += int(ok)
            rows.append({"dokument": document, "zmienna": variable, "wynik AI": actual, "klucz": None if null_value(target) else target,
                         "zgodność": ok, "typ rozbieżności": "" if ok else discrepancy(actual, target, variable, factors)})
        documents.append({"dokument": document, "zgodne": correct, "pola": len(fields), "dokładność %": 100 * correct / len(fields), "uwaga": ""})
    comparisons = pd.DataFrame(rows, columns=["dokument", "zmienna", "wynik AI", "klucz", "zgodność", "typ rozbieżności"])
    per_doc = pd.DataFrame(documents)
    total_fields = sum(d["pola"] for d in documents)
    accuracy = 100 * sum(d["zgodne"] for d in documents) / total_fields if total_fields else None
    return comparisons, per_doc, accuracy
