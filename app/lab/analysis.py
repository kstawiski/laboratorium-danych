from __future__ import annotations
import re
import numpy as np
import pandas as pd

MISSING = {"", "brak", "nd", "b.d.", "b.d", "-", "999", "-9", "null", "nan", "none", "na", "n/a"}


def normalize_id(value) -> str:
    if pd.isna(value):
        return ""
    value = str(value).strip().upper()
    match = re.fullmatch(r"([A-Z][A-Z0-9]*?)[\s_-]*(\d{1,6})", value)
    return f"{match[1]}-{int(match[2]):03d}" if match else re.sub(r"\s+", "", value)


def missing_codes(spec=None) -> set[str]:
    if spec is None or str(spec).strip().lower() in {"", "nan", "none", "pusta komórka", "pusta komorka"} or str(spec).strip().lower().startswith("pusta komórka;"):
        return MISSING
    # Kody ze słownika mają pierwszeństwo, np. 999 może być poprawnym NT-proBNP.
    return {"", "null", "nan", "none"} | {v.strip().lower() for v in re.split(r"[;,|]", str(spec))}


def is_missing(value, codes=None) -> bool:
    if value is None or pd.isna(value):
        return True
    token = str(value).strip().lower()
    chosen = MISSING if codes is None else codes
    if token in chosen:
        return True
    if re.fullmatch(r"-?\d+\.0+", token):
        return token.split(".")[0] in chosen
    return False


def missing_mask(series, codes=None) -> pd.Series:
    return series.map(lambda v: is_missing(v, codes))


def numeric_value(value, codes=None) -> float:
    if is_missing(value, codes):
        return np.nan
    # Jeden jednoznaczny wynik. Zakresów takich jak „45–50” nie zgadujemy.
    text = str(value).strip().replace("\u00a0", " ")
    match = re.fullmatch(r"([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))(?:\s*(?:%|kg|cm|mg/dl|ng/l|pg/ml|mmhg|mg/m2|ng/ml|ng/dl|g/dl|gy))?", text, re.I)
    return float(match[1].replace(",", ".")) if match else np.nan


def numeric_series(series, codes=None) -> pd.Series:
    return series.map(lambda v: numeric_value(v, codes)).astype(float)


def parse_date(value):
    if is_missing(value):
        return pd.NaT
    if isinstance(value, (pd.Timestamp,)) or hasattr(value, "year"):
        return pd.Timestamp(value).normalize()
    token = str(value).strip()
    if re.fullmatch(r"\d{5}(?:\.0+)?", token):
        return pd.Timestamp("1899-12-30") + pd.to_timedelta(float(token), unit="D")
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y.%m.%d"):
        try:
            return pd.to_datetime(token, format=fmt, errors="raise")
        except (ValueError, TypeError):
            pass
    return pd.NaT


def canonical_date(value) -> bool:
    if hasattr(value, "year"):
        return True
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value).strip())) and not pd.isna(parse_date(value))


def category_values(spec) -> list[str]:
    text = str(spec).strip()
    if text.startswith("["):
        import json
        try:
            return [str(x) for x in json.loads(text)]
        except ValueError:
            pass
    return [v.strip() for v in re.split(r"[;,|/]", text) if v.strip()]


def describe(frame: pd.DataFrame, definitions: pd.DataFrame) -> pd.DataFrame:
    specs = definitions.set_index("zmienna").to_dict("index")
    rows = []
    for name in frame:
        values = frame[name]
        spec = specs.get(name, {})
        codes = missing_codes(spec.get("kod_braku"))
        missing = missing_mask(values, codes)
        present = values[~missing]
        expected = spec.get("typ", "poza słownikiem")
        if present.empty:
            inferred = "brak wartości"
        elif present.map(lambda v: not np.isnan(numeric_value(v, codes))).all():
            numbers = numeric_series(present, codes)
            inferred = "liczba_calkowita" if (numbers % 1 == 0).all() else "liczba"
        elif present.map(canonical_date).all():
            inferred = "data"
        else:
            inferred = "tekst / mieszane"
        rows.append({"zmienna": name, "typ wykryty": inferred, "typ oczekiwany": expected,
                     "braki": int(missing.sum()), "ukryte braki": int((missing & values.map(lambda v: not (pd.isna(v) or str(v).strip() == ""))).sum()),
                     "unikalne": int(present.nunique())})
    return pd.DataFrame(rows)


def outliers(frame: pd.DataFrame, variable: str, spec: dict) -> pd.DataFrame:
    nums = numeric_series(frame[variable], missing_codes(spec.get("kod_braku")))
    q1, q3 = nums.quantile([0.25, 0.75])
    iqr = q3 - q1
    iqr_mask = ((nums < q1 - 1.5 * iqr) | (nums > q3 + 1.5 * iqr)).fillna(False)
    low, high = numeric_value(spec.get("zakres_min"), set()), numeric_value(spec.get("zakres_max"), set())
    range_mask = (nums < low) | (nums > high)
    rows = []
    for index in frame.index[iqr_mask | range_mask]:
        rows.append({"wiersz": int(index) + 2, "patient_id": str(frame.at[index, "patient_id"]) if "patient_id" in frame else "",
                     "zmienna": variable, "wartosc": str(frame.at[index, variable]),
                     "IQR": bool(iqr_mask.at[index]), "poza zakresem": bool(range_mask.at[index])})
    return pd.DataFrame(rows, columns=["wiersz", "patient_id", "zmienna", "wartosc", "IQR", "poza zakresem"])


def eda_payload(frame: pd.DataFrame, variable: str, spec: dict) -> dict:
    nums = numeric_series(frame[variable], missing_codes(spec.get("kod_braku")))
    stats = nums.describe().replace([np.inf, -np.inf], np.nan).to_dict()
    flagged = outliers(frame, variable, spec)
    # Nie przekazujemy ID, numerów wierszy, notes ani całego pliku.
    return {"zmienna": variable, "jednostka": spec.get("jednostka", ""),
            "statystyki": {k: None if pd.isna(v) else float(v) for k, v in stats.items()},
            "odstajace": flagged[["wartosc", "IQR", "poza zakresem"]].to_dict("records")}
