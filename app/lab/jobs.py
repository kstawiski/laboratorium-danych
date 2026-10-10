"""Jednakowe polecenia, schematy i limity dla UI i prewarm."""
from dataclasses import dataclass
from .data import dictionary, scenario, registry_file, read_table, extraction_prompt, extraction_schema
from .prompts import (extraction_messages, clinical_messages, SUSPICION_SCHEMA,
                      EXTRACTION_MAX_TOKENS, CLINICAL_MAX_TOKENS, CLINICAL_BATCH_SIZE)

@dataclass(frozen=True)
class ModelJob:
    name: str
    messages: list[dict]
    schema: dict
    max_tokens: int
    tab: str
    score_extraction: bool = False


def extraction_job(name, text, prompt, schema):
    return ModelJob(name, extraction_messages(text, prompt), schema, EXTRACTION_MAX_TOKENS,
                    'AI: ekstrakcja z dokumentów', True)


def clinical_jobs(frame, definitions, metadata, first=1, last=20, include_notes=False):
    selected = frame.iloc[first-1:last]
    for offset in range(0, len(selected), CLINICAL_BATCH_SIZE):
        batch = selected.iloc[offset:offset+CLINICAL_BATCH_SIZE]
        yield ModelJob(f'wiersze {first+offset}–{first+offset+len(batch)-1}',
                       clinical_messages(batch, definitions, include_notes, metadata),
                       SUSPICION_SCHEMA, CLINICAL_MAX_TOKENS, 'AI: wiarygodność kliniczna')


def default_jobs(path):
    schema, prompt = extraction_schema(path), extraction_prompt(path)
    jobs = [extraction_job(file.name, file.read_text(encoding='utf-8'), prompt, schema)
            for file in sorted((path/'dokumenty').glob('DOK-*.txt'))]
    jobs.extend(clinical_jobs(read_table(registry_file(path)), dictionary(path), scenario(path), last=120))
    return jobs
