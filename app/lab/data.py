from __future__ import annotations
from io import BytesIO, StringIO
from pathlib import Path
import csv
import json
import zipfile
import pandas as pd

DICTIONARY_COLUMNS = ["zmienna", "etykieta", "typ", "jednostka", "dozwolone_wartosci", "zakres_min", "zakres_max", "kod_braku", "regula_walidacyjna", "uwagi"]
FINDING_COLUMNS = ["patient_id", "zmienna", "problem", "decyzja"]


def read_table(source, name: str | None = None) -> pd.DataFrame:
    filename = name or str(source)
    if filename.lower().endswith(".xlsx"):
        result = pd.read_excel(source, dtype=object, keep_default_na=False)
    else:
        if hasattr(source, "getvalue"):
            content = source.getvalue()
        elif hasattr(source, "read"):
            content = source.read()
        else:
            content = Path(source).read_bytes()
        raw = content.decode("utf-8-sig") if isinstance(content, bytes) else content
        if not raw.strip():
            raise ValueError("Plik CSV jest pusty.")
        try:
            delimiter = csv.Sniffer().sniff(raw[:8192], delimiters=";,\t").delimiter
        except csv.Error:
            delimiter = ";" if ";" in raw.splitlines()[0] else ","
        result = pd.read_csv(StringIO(raw), sep=delimiter, dtype=object, keep_default_na=False)
    result.columns = [str(c).strip() for c in result.columns]
    if result.columns.duplicated().any():
        raise ValueError("Nazwy kolumn muszą być unikalne.")
    return result.reset_index(drop=True)


def dictionary(path: Path) -> pd.DataFrame:
    result = read_table(path / "slownik_danych.csv")
    # Kontrakt opisuje typ słownie; tolerujemy opisowe nagłówki autorów pakietu A.
    result.columns = [c.split(" (")[0] for c in result.columns]
    if not {"zmienna", "typ"}.issubset(result.columns):
        raise ValueError("Słownik musi zawierać kolumny zmienna i typ.")
    for column in DICTIONARY_COLUMNS:
        if column not in result:
            result[column] = ""
    if (path / "scenariusz.json").exists():
        ranges = scenario(path).get("zakresy", {})
        for index, row in result.iterrows():
            bounds = ranges.get(row["zmienna"], {})
            for column, alias in (("zakres_min", "min"), ("zakres_max", "max")):
                if str(row[column]).strip().lower() in {"", "nan", "none"} and bounds.get(alias) is not None:
                    result.at[index, column] = str(bounds[alias])
    return result


def scenario(path: Path) -> dict:
    value = json.loads((path / "scenariusz.json").read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or not value.get("nazwa"):
        raise ValueError("scenariusz.json musi zawierać nazwę scenariusza.")
    return value


def registry_file(path: Path) -> Path:
    for ext in ("xlsx", "csv"):
        file = path / f"rejestr_brudny.{ext}"
        if file.exists():
            return file
    raise ValueError("Brak rejestr_brudny.xlsx lub rejestr_brudny.csv w DATA_DIR.")


def package_problem(path: Path) -> str | None:
    try:
        definitions = dictionary(path)
        if definitions.zmienna.duplicated().any() or "patient_id" not in set(definitions.zmienna):
            return "Słownik musi mieć unikalne zmienne i pole patient_id."
        scenario(path)
        registry_file(path)
        for name in ("reguly.yaml", "ekstrakcja_prompt.txt", "ekstrakcja_schemat.json"):
            if not (path / name).is_file():
                return f"Brak {name} w DATA_DIR."
    except (OSError, ValueError, UnicodeError) as exc:
        return f"Nie można odczytać pakietu DATA_DIR: {exc}"
    return None


def id_constraints(definitions: pd.DataFrame, metadata: dict | None = None) -> dict:
    """Format i zakres ze słownika; JSON jest źródłem zapasowym."""
    import re
    rows = definitions[definitions.zmienna == "patient_id"]
    if not rows.empty:
        row = rows.iloc[0]
        for column in ("wzorzec", "pattern"):
            if row.get(column):
                return {"pattern": str(row[column])}
        text = str(row.get("regula_walidacyjna", ""))
        match = re.search(r"([A-Za-z][A-Za-z0-9_]*)-(\d+)\s*(?:\.\.|…|–)\s*(?:\1-)?(\d+)", text)
        if match:
            prefix, low, high = match.groups()
            return {"pattern": rf"{re.escape(prefix)}-\d{{{len(low)}}}", "min": int(low), "max": int(high)}
    meta = metadata or {}
    value = meta.get("patient_id", meta.get("identyfikator", {}))
    if isinstance(value, str):
        return {"pattern": value}
    if value:
        return {key: val for key, val in {
            "pattern": value.get("pattern", value.get("wzorzec", ".+")),
            "min": value.get("min", value.get("zakres_min")),
            "max": value.get("max", value.get("zakres_max"))}.items() if val is not None}
    return {"pattern": meta.get("patient_id_pattern", meta.get("wzorzec_id", ".+"))}


def conversion_factors(definitions: pd.DataFrame) -> dict[str, list[float]]:
    import re
    result = {}
    for row in definitions.to_dict("records"):
        factors = [float(x.replace(",", ".")) for x in re.findall(r"[÷×]\s*([0-9]+(?:[.,][0-9]+)?)", str(row.get("regula_walidacyjna", "")))]
        if factors:
            result[row["zmienna"]] = factors
    return result


def excel_bytes(frame: pd.DataFrame, sheet: str = "dane") -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name=sheet)
    return buffer.getvalue()


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, sep=";").encode("utf-8-sig")


def document_zip(path: Path) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted((path / "dokumenty").glob("DOK-*.txt")):
            archive.writestr(file.name, file.read_bytes())
    return buffer.getvalue()


def extraction_schema(path: Path) -> dict:
    schema = json.loads((path / "ekstrakcja_schemat.json").read_text(encoding="utf-8"))
    # Dopuszcza surowy JSON Schema albo opakowanie response_format.
    return schema.get("json_schema", {}).get("schema", schema.get("schema", schema))


def extraction_prompt(path: Path) -> str:
    return (path / "ekstrakcja_prompt.txt").read_text(encoding="utf-8-sig").strip()


def json_records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", force_ascii=False, date_format="iso"))
