#!/usr/bin/env python3
"""Próba generalna: wyniki referencyjne domyślnych zadań AI i reguł (z pamięci podręcznej po prewarm).

Uruchom w kontenerze po prewarm: python proba_generalna.py [--model Ornith]
Zapisuje wyniki do LOG_DIR/proba_generalna/. Nie zmienia pakietu danych.
"""
import argparse, json
from pathlib import Path
import pandas as pd
from lab.config import data_dir, log_dir, model_configs
from lab.data import dictionary, scenario, registry_file, read_table, extraction_schema, conversion_factors
from lab.jobs import default_jobs
from lab.llm import call_model, ModelError
from lab.rules import package_rules, run_rules
from lab.scoring import compare_findings, compare_extraction
from lab.prompts import DEFAULT_TEMPERATURE


def main():
    configs = model_configs()
    if not configs:
        print('Nie uruchomiono próby: administrator musi skonfigurować adres modelu ORNITH_BASE_URL lub QWEN_BASE_URL.')
        return 1
    ap = argparse.ArgumentParser(); ap.add_argument("--model", choices=list(configs), default=next(iter(configs))); args = ap.parse_args()
    path = data_dir(); out = log_dir() / "proba_generalna" / args.model.lower(); out.mkdir(parents=True, exist_ok=True)
    config = configs[args.model]
    definitions = dictionary(path); metadata = scenario(path); frame = read_table(registry_file(path))
    extraction, suspicions, failures, cached = {}, [], [], 0
    for job in default_jobs(path):
        try:
            r = call_model(config, job.messages, job.schema, temperature=DEFAULT_TEMPERATURE, max_tokens=job.max_tokens,
                           score_extraction=job.score_extraction, group="proba", tab=job.tab)
        except ModelError as exc:
            failures.append({"zadanie": job.name, "blad": str(exc)}); continue
        cached += int(r.cached)
        if job.score_extraction:
            extraction[job.name] = r.value
        else:
            for item in r.value.get("podejrzenia", []):
                suspicions.append(item)
    gold = read_table(path / "ekstrakcja_klucz.csv")
    fields = list(extraction_schema(path)["properties"].keys())
    comparisons, per_doc, accuracy = compare_extraction(extraction, gold, fields, conversion_factors(definitions))
    rules, problems = package_rules(path, definitions)
    rule_hits = run_rules(frame, definitions, rules)
    ai = pd.DataFrame(suspicions)
    key = read_table(path / "klucz_bledow.csv"); traps = read_table(path / "pulapki_nie_bledy.csv")
    metrics, detail, false = compare_findings(key, {"Reguły": rule_hits, "AI (Ornith)": ai}, traps)
    by_cat = detail.groupby("kategoria")[["Reguły", "AI (Ornith)"]].sum().astype(int)
    by_cat["wszystkie"] = detail.groupby("kategoria").size()
    errs = comparisons[~comparisons["zgodność"]]
    summary = {
        "model": args.model, "zadania_z_pamieci": cached, "bledy_wywolan": failures,
        "ekstrakcja": {"dokumenty": len(per_doc), "pola_na_dokument": len(fields), "dokladnosc_%": round(accuracy, 1) if accuracy is not None else None,
                       "dokladnosc_min_max_%": [round(per_doc["dokładność %"].min(), 1), round(per_doc["dokładność %"].max(), 1)],
                       "rozbieznosci_wg_typu": errs["typ rozbieżności"].value_counts().to_dict(),
                       "rozbieznosci_wg_zmiennej": errs["zmienna"].value_counts().head(10).to_dict()},
        "wiarygodnosc": {"zgloszenia_AI": len(ai), "metryki": metrics.to_dict("records"),
                         "wg_kategorii": by_cat.reset_index().to_dict("records"),
                         "falszywe_alarmy_AI_na_pulapkach": false[(false["źródło"] == "AI (Ornith)") & (false["pułapka (poprawna wartość)"])].to_dict("records")},
    }
    (out / "podsumowanie.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    comparisons.to_csv(out / "ekstrakcja_porownanie.csv", index=False); per_doc.to_csv(out / "ekstrakcja_dokumenty.csv", index=False)
    ai.to_csv(out / "podejrzenia_ai.csv", index=False); rule_hits.to_csv(out / "naruszenia_regul.csv", index=False)
    metrics.to_csv(out / "metryki.csv", index=False); false.to_csv(out / "falszywe_alarmy.csv", index=False); by_cat.to_csv(out / "wykrycia_wg_kategorii.csv")
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str)[:4000])


if __name__ == "__main__":
    raise SystemExit(main())
