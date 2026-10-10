# Laboratorium danych

Materiały do zajęć „Przygotowanie i higiena danych, systemy data capture i narzędzia walidacyjne” dla lekarzy (studia podyplomowe, Uniwersytet Medyczny w Łodzi, 2026). Autor: Konrad Stawiski.

Repozytorium zawiera:

- `app/` — aplikację Streamlit „Laboratorium danych”: EDA (eksploracyjna analiza danych), reguły walidacyjne, ekstrakcja danych z dokumentów przez lokalny model językowy, ocena wiarygodności klinicznej przez model i porównanie zgłoszeń człowieka, reguł i AI z kluczem. Instrukcja uruchomienia: [app/README.md](app/README.md).
- `exercises/` — w pełni syntetyczny pakiet ćwiczeniowy PROSTATA-RT (120 mężczyzn z rakiem gruczołu krokowego leczonych radioterapią, 56 celowo wstrzykniętych błędów, 5 rzadkich, ale poprawnych wartości, 60 syntetycznych dokumentów do ekstrakcji z kluczem) wraz z deterministycznym generatorem i testami: [exercises/README_dane.md](exercises/README_dane.md).
- `materialy/` — instrukcja ćwiczeń dla uczestników i instrukcja uruchomienia modelu Ornith-1.5-9B na własnym komputerze.

**Wszystkie dane są syntetyczne.** Imiona i nazwiska są fikcyjne, a numery w formacie PESEL mają celowo błędną cyfrę kontrolną. Nie wgrywaj do aplikacji prawdziwych danych pacjentów. Prawdziwe dane przetwarzaj tylko w środowisku zatwierdzonym przez instytucję, z wymaganymi zabezpieczeniami; na zajęciach rekomendujemy model lokalny. Aplikacja jest narzędziem dydaktycznym, a nie wyrobem medycznym.

## Szybki start (lokalnie)

1. Zainstaluj [Ollama](https://ollama.com) i uruchom `ollama run ornith-1.5:9b` (albo w [LM Studio](https://lmstudio.ai) pobierz `ornith-ai/Ornith-1.5-9B-GGUF`, wariant Q4_K_M).
2. W katalogu `app/`: `pip install -r requirements.txt`, potem ustaw `ORNITH_BASE_URL=http://localhost:11434/v1` i `ORNITH_MODEL=ornith-1.5:9b`.
3. `streamlit run app.py` — aplikacja sama znajdzie pakiet w `../exercises/dane`.

Model: [ornith-ai/Ornith-1.5-9B](https://huggingface.co/ornith-ai/Ornith-1.5-9B), licencja MIT.

## English summary

Teaching materials for a data hygiene workshop for physicians: a Streamlit app (EDA, validation rules, local-LLM extraction from clinical notes, AI plausibility checks, scoring against an answer key), a fully synthetic prostate cancer radiotherapy registry with 56 injected errors and 20 synthetic clinical notes, and Polish handouts. Runs with any OpenAI-compatible local server (Ollama, LM Studio). Synthetic data only; not a medical device. MIT licence.
