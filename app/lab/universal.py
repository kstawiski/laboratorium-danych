"""Walidacja schematów i materiałów dostarczonych w sesji."""
import json
import math
import re
from pathlib import PurePath
import pandas as pd
from .data import DICTIONARY_COLUMNS

MINIMAL_SCHEMA = {'type': 'object', 'properties': {'patient_id': {'type': ['string', 'null']}},
                  'required': ['patient_id'], 'additionalProperties': False}
DEFAULT_PROMPT = 'Wyodrębnij dane z syntetycznego dokumentu według schematu. Nie zgaduj brakujących wartości; użyj null.'
MAX_DOCUMENTS = 20
MAX_DOCUMENT_BYTES = 100_000


def own_dictionary(table):
    if not {'zmienna', 'typ'}.issubset(table):
        raise ValueError('Słownik musi zawierać kolumny zmienna i typ.')
    table = table.copy().fillna('')
    for column in ('zmienna', 'typ'):
        table[column] = table[column].astype(str).str.strip()
    if table.empty or table.zmienna.eq('').any() or table.typ.eq('').any() or table.zmienna.duplicated().any():
        raise ValueError('Słownik musi mieć unikalne, niepuste zmienne i niepuste typy.')
    for column in DICTIONARY_COLUMNS:
        if column not in table:
            table[column] = ''
    return table


def validate_extraction_schema(text):
    def reject(_):
        raise ValueError('JSON nie może zawierać NaN ani Infinity.')
    try:
        schema = json.loads(text, parse_constant=reject)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError('Schemat musi być poprawnym JSON.') from exc
    if not isinstance(schema, dict) or schema.get('type') != 'object' or not isinstance(schema.get('properties'), dict) or not schema['properties']:
        raise ValueError('Schemat musi mieć type: object i niepuste properties.')
    allowed = {'type', 'properties', 'required', 'additionalProperties', 'items', 'maxItems', 'anyOf',
               'enum', 'minimum', 'maximum', 'pattern', 'format', '$schema', 'title', 'description'}
    types = {'object', 'array', 'string', 'number', 'integer', 'boolean', 'null'}
    def check(node, location):
        if not isinstance(node, dict):
            raise ValueError(f'{location}: definicja pola musi być obiektem.')
        unsupported = set(node) - allowed
        if unsupported:
            raise ValueError(f'{location}: nieobsługiwane słowa schematu: {", ".join(sorted(unsupported))}.')
        for name in ('$schema', 'title', 'description'):
            if name in node and not isinstance(node[name], str):
                raise ValueError(f'{location}: {name} musi być tekstem.')
        kind = node.get('type', [])
        kind = [kind] if isinstance(kind, str) else kind
        if not isinstance(kind, list) or any(not isinstance(t, str) or t not in types for t in kind):
            raise ValueError(f'{location}: nieobsługiwany typ.')
        if 'format' in node and node['format'] != 'date':
            raise ValueError(f'{location}: obsługiwany format to date.')
        if 'pattern' in node:
            try:
                re.compile(node['pattern'])
            except (re.error, TypeError) as exc:
                raise ValueError(f'{location}: niepoprawny pattern.') from exc
        for bound in ('minimum', 'maximum'):
            if bound in node and (isinstance(node[bound], bool) or not isinstance(node[bound], (int, float)) or not math.isfinite(node[bound])):
                raise ValueError(f'{location}: {bound} musi być skończoną liczbą.')
        if node.get('minimum', -math.inf) > node.get('maximum', math.inf):
            raise ValueError(f'{location}: minimum przekracza maximum.')
        if 'maxItems' in node and (type(node['maxItems']) is not int or node['maxItems'] < 0):
            raise ValueError(f'{location}: maxItems musi być nieujemną liczbą całkowitą.')
        if 'additionalProperties' in node and type(node['additionalProperties']) is not bool:
            raise ValueError(f'{location}: additionalProperties musi być true lub false.')
        if 'enum' in node and (not isinstance(node['enum'], list) or not node['enum']):
            raise ValueError(f'{location}: enum musi być niepustą listą.')
        properties = node.get('properties', {})
        if not isinstance(properties, dict):
            raise ValueError(f'{location}: properties musi być obiektem.')
        required = node.get('required', [])
        if not isinstance(required, list) or any(not isinstance(n, str) or n not in properties for n in required):
            raise ValueError(f'{location}: required musi wskazywać pola z properties.')
        for name, child in properties.items():
            check(child, location + '.' + name)
        if 'items' in node:
            check(node['items'], location + '[]')
        if 'anyOf' in node:
            if set(node) - {'anyOf', '$schema', 'title', 'description'}:
                raise ValueError(f'{location}: anyOf nie można łączyć z innymi ograniczeniami w tym samym obiekcie.')
            if not isinstance(node['anyOf'], list) or not node['anyOf']:
                raise ValueError(f'{location}: anyOf musi być niepustą listą.')
            for child in node['anyOf']:
                check(child, location + '.anyOf')
    try:
        check(schema, 'Schemat')
    except RecursionError as exc:
        raise ValueError('Schemat jest zbyt złożony.') from exc
    return schema


def schema_fields(schema):
    rows = []
    for name, spec in schema['properties'].items():
        limits = {key: spec[key] for key in ('enum', 'minimum', 'maximum', 'pattern', 'format', 'anyOf') if key in spec}
        rows.append({'pole': name, 'typ': json.dumps(spec.get('type', []), ensure_ascii=False),
                     'dozwolone wartości / zakres': json.dumps(limits, ensure_ascii=False) if limits else ''})
    return pd.DataFrame(rows)


def add_document(documents, name, content):
    name = name.strip()
    if not name or len(name) > 120 or PurePath(name).name != name or '\\' in name or any(ord(c) < 32 for c in name):
        raise ValueError('Podaj krótką nazwę pliku bez ścieżki.')
    if not name.lower().endswith(('.txt', '.md')):
        raise ValueError('Dokument musi mieć rozszerzenie .txt lub .md.')
    raw = content.encode('utf-8') if isinstance(content, str) else content
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError('Dokument może mieć najwyżej 100 kB.')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('Dokument musi być zapisany jako UTF-8.') from exc
    if not text.strip():
        raise ValueError('Dokument jest pusty.')
    key = 'własny:' + name
    if key not in documents and len(documents) >= MAX_DOCUMENTS:
        raise ValueError('Możesz dodać najwyżej 20 własnych dokumentów.')
    documents[key] = text
    return key
