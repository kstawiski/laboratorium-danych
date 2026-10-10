#!/usr/bin/env python3
"""Wypełnienie CACHE_DIR domyślnymi zapytaniami. Nie zmienia pakietu danych."""
import argparse
from lab.config import data_dir, cache_dir, model_configs
from lab.data import package_problem
from lab.jobs import default_jobs
from lab.llm import call_model, ModelError, _cache_key, prepared_messages
from lab.prompts import DEFAULT_TEMPERATURE


def run_prewarm(path, config, temperature=DEFAULT_TEMPERATURE, caller=call_model, dry_run=False):
    problem = package_problem(path)
    if problem:
        raise ValueError(problem)
    jobs = default_jobs(path)
    hits, failures = 0, []
    for index, job in enumerate(jobs, 1):
        if dry_run:
            digest = _cache_key(config, prepared_messages(job.messages, job.schema), temperature, job.max_tokens)
            print(f'{index}/{len(jobs)} {job.name}: {digest} ({job.max_tokens} tokenów)')
            continue
        try:
            result = caller(config, job.messages, job.schema, temperature=temperature,
                            max_tokens=job.max_tokens, score_extraction=job.score_extraction,
                            group='prewarm', tab=job.tab)
            hits += int(result.cached)
            print(f'{index}/{len(jobs)} {job.name}: {result.elapsed:.1f} s; ' +
                  ('pamięć podręczna' if result.cached else 'serwer'), flush=True)
        except ModelError as exc:
            failures.append(job.name)
            print(f'{index}/{len(jobs)} {job.name}: BŁĄD: {exc}', flush=True)
    print(f'Zapytania: {len(jobs)}; z pamięci: {hits}; błędy: {len(failures)}; CACHE_DIR={cache_dir()}')
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=['Ornith', 'Qwen'], default='Ornith')
    parser.add_argument('--temperature', type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument('--dry-run', action='store_true', help='Lista zapytań i hashy; bez kontaktu z modelem.')
    args = parser.parse_args()
    try:
        failures = run_prewarm(data_dir(), model_configs()[args.model], args.temperature, dry_run=args.dry_run)
        return 1 if failures else 0
    except (OSError, ValueError) as exc:
        print(f'Nie uruchomiono prewarm: {exc}')
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
