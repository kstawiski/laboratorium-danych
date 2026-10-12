"""Reguły z pakietu danych. Wyrażenia interpretowane przez listę dozwolonych operacji."""
from __future__ import annotations
import ast
from dataclasses import dataclass, asdict, field, replace
from io import StringIO
from pathlib import Path
import json
import operator
import math
import re
import tokenize
import numpy as np
import pandas as pd
import yaml
from .analysis import (missing_mask, missing_codes, numeric_series, numeric_value,
                       normalize_id, category_values, parse_date, canonical_date)
from .data import id_constraints, scenario

RESULT_COLUMNS = ['wiersz', 'patient_id', 'zmienna', 'wartosc', 'regula', 'typ', 'powaga']

@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    kind: str
    variable: str = ''
    minimum: float | None = None
    maximum: float | None = None
    expression: str = ''
    values: tuple = ()
    severity: str = 'ostrzezenie'
    parameters: dict = field(default_factory=dict)
    display_type: str = ''

    def to_dict(self):
        return asdict(self)

    @property
    def category(self):
        return self.display_type or {'range': 'zakres', 'category': 'format', 'date': 'format',
            'numeric': 'format', 'integer': 'format', 'id': 'format', 'required': 'format',
            'unique': 'unikalność', 'duplicate': 'unikalność', 'age': 'czas',
            'chronology': 'czas', 'unit': 'format'}.get(self.kind, 'spójność')

ALLOWED_KINDS = {'range', 'category', 'date', 'numeric', 'integer', 'id', 'required',
                 'unique', 'duplicate', 'age', 'chronology', 'unit', 'query'}


def finite_bound(value):
    result = numeric_value(value, set())
    return None if np.isnan(result) else result


def _tree(expression, package=False):
    if len(expression) > 8000:
        raise ValueError('Wyrażenie jest za długie.')
    try:
        # Priorytety jak w pandas query, również dla a == 1 & b == 2.
        tokens = [(tokenize.NAME if t.type == tokenize.OP and t.string in {'&', '|', '~'} else t.type,
                   {'&': 'and', '|': 'or', '~': 'not'}.get(t.string, t.string) if t.type == tokenize.OP else t.string)
                  for t in tokenize.generate_tokens(StringIO(expression).readline)]
        tree = ast.parse(tokenize.untokenize(tokens).strip(), mode='eval')
    except (SyntaxError, tokenize.TokenError) as exc:
        raise ValueError('Niepoprawny warunek naruszenia.') from exc
    if sum(1 for _ in ast.walk(tree)) > 600:
        raise ValueError('Wyrażenie jest zbyt złożone.')
    return tree


def query_mask(frame: pd.DataFrame, expression: str, *, package=False) -> pd.Series:
    """Bez eval. Metody z pakietu są ograniczone do predykatów pandas."""
    root = _tree(expression, package)
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Eq: operator.eq,
           ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
           ast.Gt: operator.gt, ast.GtE: operator.ge}
    def as_number(value):
        # Kolumny tekstowo-liczbowe (np. '0,2' obok 'ok. 0,2') porównujemy liczbowo; tekst -> brak (NaN).
        if isinstance(value, pd.Series) and not pd.api.types.is_numeric_dtype(value) and not pd.api.types.is_bool_dtype(value):
            return pd.to_numeric(value.astype(str).str.strip().str.replace(',', '.', regex=False), errors='coerce')
        return value
    numeric_like = lambda v: (isinstance(v, (int, float)) and not isinstance(v, bool)) or (isinstance(v, pd.Series) and pd.api.types.is_numeric_dtype(v) and not pd.api.types.is_bool_dtype(v))
    def visit(node):
        if isinstance(node, ast.Name) and node.id in frame:
            return frame[node.id]
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, float, int, bool, type(None))):
            return node.value
        if package and isinstance(node, (ast.List, ast.Tuple)):
            return [visit(n) for n in node.elts]
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](as_number(visit(node.left)), as_number(visit(node.right)))
        if isinstance(node, ast.Compare):
            left, result = visit(node.left), pd.Series(True, index=frame.index)
            for op, right_node in zip(node.ops, node.comparators):
                if type(op) not in ops:
                    raise ValueError('Dozwolone porównania: ==, !=, <, <=, >, >=.')
                right = visit(right_node)
                if isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)) or numeric_like(left) or numeric_like(right):
                    left, right = as_number(left), as_number(right)
                compared = ops[type(op)](left, right)
                result &= compared.fillna(False) if isinstance(compared, pd.Series) else compared
                left = right
            return result
        if isinstance(node, ast.BoolOp):
            result = visit(node.values[0])
            for next_node in node.values[1:]:
                result = (result & visit(next_node)) if isinstance(node.op, ast.And) else (result | visit(next_node))
            return result
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.Invert, ast.USub, ast.UAdd)):
            value = visit(node.operand)
            if isinstance(node.op, (ast.Not, ast.Invert)):
                return ~value if isinstance(value, pd.Series) else not value
            return -value if isinstance(node.op, ast.USub) else value
        if package and isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func
            strings = isinstance(attr.value, ast.Attribute) and attr.value.attr == 'str'
            target = attr.value.value if strings else attr.value
            if not isinstance(target, ast.Name) or target.id not in frame:
                raise ValueError('Metoda może dotyczyć tylko kolumny.')
            series = frame[target.id]
            args = [visit(n) for n in node.args]
            kwargs = {k.arg: visit(k.value) for k in node.keywords if k.arg in {'case', 'keep', 'regex', 'na'}}
            if len(kwargs) != len(node.keywords):
                raise ValueError('Nieobsługiwany parametr metody.')
            if strings and attr.attr in {'contains', 'fullmatch', 'startswith', 'endswith'}:
                return getattr(series.astype(str).str, attr.attr)(*args, **kwargs)
            if not strings and attr.attr in {'isin', 'duplicated', 'isna', 'notna'}:
                return getattr(series, attr.attr)(*args, **kwargs)
        raise ValueError('Dozwolone są nazwy kolumn, porównania, and/or/not i + - * /. Bez kodu Python.')
    try:
        result = visit(root.body)
    except (TypeError, ZeroDivisionError, AttributeError) as exc:
        raise ValueError('Niezgodne typy w wyrażeniu.') from exc
    if not isinstance(result, pd.Series) or not pd.api.types.is_bool_dtype(result):
        raise ValueError('Wyrażenie musi dawać warunek logiczny dla każdego wiersza.')
    return result.fillna(False)


def validate_rule(raw: dict, columns: set[str]) -> Rule:
    if not isinstance(raw, dict):
        raise ValueError('Reguła musi być obiektem JSON.')
    kind, variable = raw.get('kind', ''), raw.get('variable', '')
    if kind not in ALLOWED_KINDS:
        raise ValueError('Nieobsługiwany typ reguły.')
    if variable not in columns:
        raise ValueError(f'Nieznana zmienna: {variable}')
    if kind == 'query':
        query_mask(pd.DataFrame({c: [1.0] for c in columns}), raw.get('expression', ''))
    for bound in (raw.get('minimum'), raw.get('maximum')):
        if bound is not None and str(bound).strip():
            if finite_bound(bound) is None or not math.isfinite(finite_bound(bound)):
                raise ValueError('Granica zakresu musi być skończoną liczbą.')
    low, high = finite_bound(raw.get('minimum')), finite_bound(raw.get('maximum'))
    if kind == 'range' and low is None and high is None:
        raise ValueError('Podaj co najmniej jedną granicę.')
    if low is not None and high is not None and low > high:
        raise ValueError('Minimum nie może przekraczać maksimum.')
    if kind == 'category' and not raw.get('values'):
        raise ValueError('Podaj dozwolone wartości.')
    return Rule(str(raw.get('id', 'custom')), str(raw.get('description', 'Reguła własna')),
                kind, str(variable), low, high, str(raw.get('expression', '')),
                tuple(raw.get('values') or ()), str(raw.get('severity', 'ostrzezenie')),
                {'missing_policy': 'skip'} if raw.get('parameters', {}).get('missing_policy') == 'skip' else {})


def default_rules(definitions, metadata=None):
    """Ogólne kontrole słownika, używane gdy katalog reguł jest pusty."""
    rules = []
    for spec in definitions.to_dict('records'):
        name, kind = spec['zmienna'], spec['typ']
        low, high = finite_bound(spec.get('zakres_min')), finite_bound(spec.get('zakres_max'))
        if low is not None or high is not None:
            rules.append(Rule(f'range:{name}', f'{name}: zakres {low}–{high}', 'range', name, low, high))
        if kind in {'liczba', 'liczba_calkowita'}:
            rules.append(Rule(f'numeric:{name}', f'{name}: pojedyncza liczba bez dopisku', 'numeric', name))
        if kind == 'liczba_calkowita':
            rules.append(Rule(f'integer:{name}', f'{name}: liczba całkowita', 'integer', name))
        if kind in {'kategoria', 'logiczna'}:
            values = category_values(spec.get('dozwolone_wartosci', ''))
            if values:
                rules.append(Rule(f'category:{name}', f'{name}: wartości ze słownika', 'category', name, values=tuple(values)))
        if kind == 'data':
            rules.append(Rule(f'date:{name}', f'{name}: pełna data ISO', 'date', name))
    rules.append(Rule('patient_id', 'ID zgodne ze słownikiem', 'id', 'patient_id', parameters=id_constraints(definitions, metadata)))
    return rules


def package_rules(path: Path, definitions) -> tuple[list[Rule], list[str]]:
    metadata = scenario(path) if (path / 'scenariusz.json').exists() else {}
    file = path / 'reguly.yaml'
    if not file.exists():
        return default_rules(definitions, metadata), ['Brak reguly.yaml; użyto kontroli słownika.']
    try:
        raw = yaml.safe_load(file.read_text(encoding='utf-8-sig')) or []
    except yaml.YAMLError:
        return default_rules(definitions, metadata), ['Niepoprawny reguly.yaml; użyto kontroli słownika.']
    raw = raw.get('reguly', raw.get('rules', [])) if isinstance(raw, dict) else raw
    if not isinstance(raw, list):
        raise ValueError('reguly.yaml musi zawierać listę reguł.')
    specs = definitions.set_index('zmienna').to_dict('index')
    result, messages = [], []
    controls = {'format_id': 'id', 'unikalny_id': 'unique', 'duplikat_rekordu': 'duplicate',
                'brak': 'required', 'kategoria': 'category', 'liczba_format': 'numeric',
                'calkowita': 'integer', 'data_iso': 'date', 'jednostka': 'unit', 'wiek': 'age'}
    labels = {'unikalnosc': 'unikalność', 'spojnosc': 'spójność', 'czas': 'czas', 'zakres': 'zakres', 'format': 'format'}
    for i, item in enumerate(raw):
        try:
            identifier = str(item.get('id', f'pakiet:{i}'))
            description = item.get('opis', item.get('description', identifier))
            kind = controls.get(item.get('kontrola'), item.get('kind', 'query'))
            if item.get('typ') == 'zakres': kind = 'range'
            if item.get('kolejnosc'): kind = 'chronology'
            if 'zmienne' not in item and 'kind' not in item:
                kind = {'zakres': 'range', 'kategoria': 'category', 'format_daty': 'date'}.get(item.get('typ'), kind)
            variables = item.get('zmienne', [item.get('variable', item.get('zmienna', ''))])
            if variables == ['*']:
                variables = [n for n, s in specs.items() if (s['typ'] != 'tekst' or n == 'patient_id')
                             and not re.search(r'pusta komórka poprawna|opcjonal', s.get('uwagi', ''), re.I)]
            expression = item.get('wyrazenie', item.get('expression', item.get('query', '')))
            parameters = dict(item, package=True)
            if kind == 'id':
                parameters.update(id_constraints(definitions, metadata))
                if parameters.get('pattern') == '.+': parameters['pattern'] = item.get('wzorzec', '.+')
            if kind == 'age':
                names = [n.id for n in ast.walk(_tree(expression)) if isinstance(n, ast.Name)]
                parameters['reference_date'] = next((n for n in names if n not in variables), '')
            bounds = item.get('zakres', {})
            for variable in variables:
                if variable not in specs:
                    raise ValueError(f'Nieznana zmienna: {variable}')
                spec = specs[variable]
                low = finite_bound(bounds.get('min', item.get('minimum', item.get('min', spec.get('zakres_min')))))
                high = finite_bound(bounds.get('max', item.get('maximum', item.get('max', spec.get('zakres_max')))))
                values = tuple(item.get('values', item.get('wartosci', category_values(spec.get('dozwolone_wartosci', '')))))
                expr = expression
                # Predykaty formatowe połączone OR oceniamy osobno dla każdej kolumny.
                if kind == 'query' and item.get('typ') == 'format':
                    tree = _tree(expression)
                    terms = tree.body.values if isinstance(tree.body, ast.BoolOp) and isinstance(tree.body.op, ast.Or) else [tree.body]
                    predicates = [n for n in terms if any(isinstance(x, ast.Name) and x.id == variable for x in ast.walk(n))]
                    if predicates:
                        expr = ' or '.join('(' + ast.unparse(n) + ')' for n in predicates)
                result.append(Rule(f'pakiet:{identifier}:{variable}', f'{variable}: {description}', kind,
                    variable, low, high, expr, values, item.get('powaga', 'ostrzezenie'),
                    parameters, labels.get(item.get('typ'), '')))
        except (ValueError, TypeError, KeyError) as exc:
            messages.append(f'Pominięto regułę {item.get("id", i)}: {exc}')
    return result or default_rules(definitions, metadata), messages


def run_rules(frame, definitions, rules):
    specs = definitions.set_index('zmienna').to_dict('index')
    def numeric(name):
        values = numeric_series(frame[name], missing_codes(specs.get(name, {}).get('kod_braku')))
        bare = frame[name].map(lambda v: bool(re.fullmatch(r'[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)', str(v).strip())))
        return values.where(bare)
    def dates(name):
        return pd.to_datetime(frame[name].map(lambda v: parse_date(v) if canonical_date(v) else pd.NaT))
    typed, valid = frame.copy(), {}
    for name in frame:
        spec = specs.get(name, {})
        valid[name] = ~missing_mask(frame[name], missing_codes(spec.get('kod_braku')))
        if spec.get('typ') in {'liczba', 'liczba_calkowita', 'logiczna'}:
            typed[name] = numeric(name)
            valid[name] &= typed[name].notna()
            for op, key in ((operator.ge, 'zakres_min'), (operator.le, 'zakres_max')):
                bound = finite_bound(spec.get(key))
                if bound is not None: valid[name] &= op(typed[name], bound)
        elif spec.get('typ') == 'data':
            valid[name] &= frame[name].map(canonical_date)
        elif spec.get('typ') == 'kategoria':
            values = category_values(spec.get('dozwolone_wartosci', ''))
            if values: valid[name] &= frame[name].astype(str).isin(values)
    results = []
    rules, skipped = available_rules(rules, set(frame))
    for rule in rules:
        name, kind = rule.variable, rule.kind
        series = frame[name]
        present = ~missing_mask(series, missing_codes(specs.get(name, {}).get('kod_braku')))
        mask = pd.Series(False, index=frame.index)
        if kind == 'required': mask = ~present
        elif kind == 'range':
            nums = numeric(name)
            if rule.minimum is not None: mask |= nums < rule.minimum
            if rule.maximum is not None: mask |= nums > rule.maximum
        elif kind == 'numeric':
            mask = present & ~series.map(lambda x: bool(re.fullmatch(r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)', str(x))))
        elif kind == 'integer': mask = present & numeric(name).notna() & (numeric(name) % 1 != 0)
        elif kind == 'category':
            tokens = series.map(lambda x: str(int(x)) if isinstance(x, (float, int)) and float(x).is_integer() else str(x))
            mask = present & ~tokens.isin(rule.values)
        elif kind == 'date': mask = present & ~series.map(canonical_date)
        elif kind == 'id':
            params = rule.parameters or id_constraints(definitions)
            def good_id(value):
                token = str(value)
                if re.fullmatch(params.get('pattern', '.+'), token) is None: return False
                tail = re.search(r'(\d+)$', token)
                return not tail or params.get('min', -math.inf) <= int(tail[1]) <= params.get('max', math.inf)
            mask = present & ~series.map(good_id)
        elif kind == 'unique': mask = present & series.map(normalize_id).duplicated(keep=False)
        elif kind == 'duplicate':
            cols = [c for c in frame if c != name]
            if cols: mask = frame[cols].astype(str).duplicated(keep='first')
        elif kind == 'unit':
            expected = str(specs[name].get('jednostka', '')).lower().replace('μ', 'µ')
            def wrong_unit(value):
                match = re.fullmatch(r'[+-]?[\d.,]+\s+([^\d]+)', str(value).strip())
                return bool(match and match[1].strip().lower().replace('μ', 'µ') != expected)
            mask = present & series.map(wrong_unit)
        elif kind == 'age':
            reference = rule.parameters.get('reference_date')
            if reference not in frame: raise ValueError(f'Brak daty odniesienia dla {rule.description}.')
            birth, at = dates(name), dates(reference)
            low, high = rule.minimum, rule.maximum
            adult = birth.map(lambda x: x + pd.DateOffset(years=int(low)) if pd.notna(x) else pd.NaT)
            oldest = birth.map(lambda x: x + pd.DateOffset(years=int(high)+1) if pd.notna(x) else pd.NaT)
            mask = birth.notna() & at.notna() & ((at < adult) | (at >= oldest))
        elif kind == 'chronology':
            # Zgłoszenie do daty po prawej stronie, chyba że wyrażenie jawnie wskazuje lewą.
            for left, right in rule.parameters['kolejnosc']:
                if not {left, right}.issubset(frame): continue
                strict = bool(re.search(rf'\b{re.escape(right)}\s*<=\s*{re.escape(left)}\b', rule.expression))
                failed = (dates(right) <= dates(left)) if strict else (dates(right) < dates(left))
                target = left if re.search(rf'\b{re.escape(left)}\s*>\s*{re.escape(right)}\b', rule.expression) else right
                if name == target: mask |= failed
        elif kind == 'query':
            package = rule.parameters.get('package', False)
            tree = _tree(rule.expression)
            referenced = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            missing_columns = referenced - set(frame)
            if missing_columns: raise ValueError('Brak kolumn reguły: ' + ', '.join(sorted(missing_columns)))
            string_columns = {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                              and n.attr == 'str' and isinstance(n.value, ast.Name)}
            query_frame = typed.copy()
            for column in string_columns: query_frame[column] = frame[column].astype(str)
            mask = query_mask(query_frame, rule.expression, package=package)
            if rule.parameters.get('missing_policy') == 'skip':
                for column in referenced:
                    mask &= ~missing_mask(frame[column], missing_codes(specs.get(column, {}).get('kod_braku')))
            if rule.display_type == 'spójność':
                empty_allowed = {n.left.id for n in ast.walk(tree) if isinstance(n, ast.Compare)
                                 and isinstance(n.left, ast.Name) and any(isinstance(c, ast.Constant) and c.value == '' for c in n.comparators)}
                for column in referenced - empty_allowed: mask &= valid[column]
        else:
            raise ValueError(f'Nieobsługiwana reguła: {rule.description}')
        for index in frame.index[mask.fillna(False)]:
            results.append({'wiersz': int(index) + 2, 'patient_id': str(frame.at[index, 'patient_id']) if 'patient_id' in frame else '',
                            'zmienna': name, 'wartosc': str(series.at[index]), 'regula': rule.description,
                            'typ': rule.category, 'powaga': rule.severity})
    result = pd.DataFrame(results, columns=RESULT_COLUMNS).drop_duplicates()
    result.attrs['skipped_rules'] = skipped
    return result


def rule_columns(rule):
    columns = {rule.variable}
    if rule.kind == 'query':
        columns |= {n.id for n in ast.walk(_tree(rule.expression)) if isinstance(n, ast.Name)}
    if rule.kind == 'age':
        columns.add(rule.parameters.get('reference_date', ''))
    if rule.kind == 'chronology':
        columns |= {name for pair in rule.parameters.get('kolejnosc', []) for name in pair}
    return columns


def available_rules(rules, columns):
    ready, skipped = [], []
    for rule in rules:
        missing = rule_columns(rule) - columns
        if missing:
            skipped.append(f"{rule.description} (brak: {', '.join(sorted(missing))})")
        else:
            ready.append(rule)
    return ready, skipped


def rule_label(rule):
    name = rule.variable
    if rule.kind == 'range':
        terms = [f'{name} < {rule.minimum:g}' if rule.minimum is not None else '',
                 f'{name} > {rule.maximum:g}' if rule.maximum is not None else '']
        return 'Oznacz, gdy ' + ' lub '.join(t for t in terms if t) + ' (braki i nieczytelne liczby pomijane).'
    if rule.kind == 'query':
        suffix = ' (wiersze z brakami pomijane)' if rule.parameters.get('missing_policy') == 'skip' else ''
        if rule.display_type == 'spójność':
            suffix += ' (ocena tylko przy poprawnych wartościach zależnych; jawny pusty tekst jest wyjątkiem)'
        return f'Oznacz, gdy {rule.expression}{suffix}.'
    predicates = {
        'required': f'{name} jest puste lub zawiera kod braku ze słownika',
        'numeric': f'{name} nie jest pojedynczą liczbą w zapisie z kropką (braki pomijane)',
        'integer': f'{name} jest liczbą niecałkowitą (braki i nieczytelne liczby pomijane)',
        'category': f'{name} jest spoza listy {list(rule.values)} (braki pomijane)',
        'date': f'{name} nie jest poprawną pełną datą ISO (braki pomijane)',
        'id': f'{name} ma format lub zakres niezgodny ze słownikiem (braki pomijane)',
        'unique': f'{name} powtarza się po ujednoliceniu ID (wszystkie wystąpienia; braki pomijane)',
        'duplicate': 'rekord powtarza wcześniejszy rekord poza ID',
        'unit': f'{name} ma dopisaną jednostkę inną niż w słowniku (braki pomijane)',
        'age': f'wiek obliczony z {name} i {rule.parameters.get("reference_date", "")} jest poza zakresem {rule.minimum}–{rule.maximum} (brak poprawnej daty pomijany)',
        'chronology': f'zachodzi naruszenie kolejności dat: {rule.expression or rule.parameters.get("kolejnosc", [])} (brak poprawnej daty pomijany)',
    }
    return 'Oznacz, gdy ' + predicates.get(rule.kind, rule.description) + '.'


def custom_rule(raw, columns, correct=False):
    raw = dict(raw)
    if raw.get('kind') == 'query':
        expression = raw.get('expression', '')
        if correct:
            expression = f'not ({expression})'
        raw['expression'] = expression
        raw['parameters'] = {'missing_policy': 'skip'}
        raw['description'] = f'Oznacz, gdy {expression} (Własna: braki pomijane).'
    else:
        raw['description'] = rule_label(validate_rule(raw, columns)) + ' Własna: zakres.'
    return validate_rule(raw, columns)


def rule_preview(frame, definitions, rule):
    results = run_rules(frame, definitions, [rule])
    indices = sorted(set(results.wiersz - 2))
    columns = [c for c in frame if c == 'patient_id' or c in rule_columns(rule)]
    return len(indices), frame.iloc[indices[:10]][columns]


def import_rules(text, frame, definitions, offset=0):
    raw = json.loads(text)
    if not isinstance(raw, list) or len(raw) > 200:
        raise ValueError('JSON musi zawierać listę najwyżej 200 reguł.')
    ready, rejected = [], []
    for index, item in enumerate(raw):
        try:
            if not isinstance(item, dict) or item.get('kind') not in {'range', 'category', 'query'}:
                raise ValueError('Własne reguły: range, category lub query.')
            item = dict(item, id=f'import:{offset + len(ready)}')
            rule = validate_rule(item, set(frame))
            rule = replace(rule, description=rule_label(rule))
            run_rules(frame, definitions, [rule])
            ready.append(rule)
        except (ValueError, TypeError, AttributeError) as exc:
            rejected.append(f'Reguła {index + 1}: {exc}')
    return ready, rejected


def rule_summary(results, rules):
    rows = []
    for rule in rules:
        flagged = results[results.regula == rule.description]
        rows.append({'reguła': rule_label(rule), 'oznaczone wiersze': flagged.wiersz.nunique(),
                     'różni pacjenci': flagged.patient_id[flagged.patient_id != ''].map(normalize_id).nunique()})
    return pd.DataFrame(rows, columns=['reguła', 'oznaczone wiersze', 'różni pacjenci'])
