# Laboratorium danych

Polska aplikacja Streamlit do zajęć z higieny danych dla lekarzy. Pozwala obejrzeć rejestr, uruchomić reguły, wyodrębnić dane z dokumentów przez model lokalny oraz porównać zgłoszenia grupy i AI z kluczem. Scenariusz, słownik, reguły i polecenie ekstrakcji pochodzą z pakietu danych. Dołączony mały zestaw próbny dotyczy PROSTATA-RT.

**Wszystkie dołączone dane są w pełni syntetyczne. Nie wklejaj ani nie wgrywaj prawdziwych danych pacjentów do demonstracji.** Ewentualne użycie prawdziwych danych wymaga środowiska zatwierdzonego przez instytucję, jej zgody i odrębnej oceny organizacji przetwarzania; rekomendujemy model lokalny. Aplikacja jest narzędziem dydaktycznym, nie wyrobem medycznym. Wynik AI wymaga sprawdzenia źródła; rzadka wartość sama w sobie nie oznacza błędu.

## Lokalnie w 3 krokach — Windows, macOS, Linux

Wymagany Python 3.12. Otwórz terminal w katalogu zawierającym `app.py`.

1. Uruchom model zgodny z OpenAI API. W Ollama wykonaj w osobnym terminalu:

   ```text
   ollama run ornith-1.5:9b
   ```

   Alternatywnie w LM Studio pobierz `ornith-ai/Ornith-1.5-9B-GGUF`, wariant Q4_K_M (około 5,8 GB; laptop z około 16 GB RAM), i uruchom serwer lokalny na `http://localhost:1234/v1`. Zmienne `ORNITH_BASE_URL` i `ORNITH_MODEL` muszą odpowiadać adresowi i identyfikatorowi modelu widocznemu w LM Studio. Dostępność modelu i zapotrzebowanie na pamięć zależą od instalacji; tych dwóch programów nie testowano w tej weryfikacji.

2. Zainstaluj zależności i ustaw konfigurację. Zalecane jest osobne środowisko wirtualne (`python -m venv .venv`; aktywacja: Windows `.venv\Scripts\Activate.ps1`, macOS/Linux `source .venv/bin/activate`).

   ```text
   pip install -r requirements.txt
   ```

   macOS/Linux, dla Ollama:

   ```bash
   export ORNITH_BASE_URL=http://localhost:11434/v1
   export ORNITH_MODEL=ornith-1.5:9b
   export DATA_DIR=tests/fixtures
   ```

   Windows PowerShell, dla Ollama:

   ```powershell
   $env:ORNITH_BASE_URL="http://localhost:11434/v1"
   $env:ORNITH_MODEL="ornith-1.5:9b"
   $env:DATA_DIR="tests/fixtures"
   ```

   Dla LM Studio ustaw `ORNITH_BASE_URL=http://localhost:1234/v1` i `ORNITH_MODEL` zgodny z nazwą modelu na serwerze. Lokalne serwery bez uwierzytelniania nie wymagają klucza. Dla pełnego pakietu wskaż jego katalog w `DATA_DIR`. Bez tej zmiennej aplikacja szuka `../exercises/dane`, następnie `./dane`; brak pakietu jest sygnalizowany i uruchamia zestaw próbny.

3. Uruchom aplikację i otwórz adres podany przez Streamlit:

   ```text
   streamlit run app.py
   ```

## Praca na zajęciach

Wpisz nazwę grupy. Każda z siedmiu zakładek podaje trzy krótkie kroki. Pobierz rejestr, słownik, dokumenty i kartę znalezisk. Kontrola kliniczna domyślnie obejmuje 20 wierszy w paczkach po 10. Ekstrakcja wielu dokumentów działa kolejno. W zakładce Porównanie rozwiązanie pojawia się po kliknięciu „Pokaż klucz”.

Wyniki modelu są domyślnie zapisywane w trwałej pamięci podręcznej. UI pokazuje czas odpowiedzi i jej źródło. Zaznaczenie „Nie używaj pamięci podręcznej (nowe zapytanie do modelu)” pomija odczyt i zapis wyniku. Cache przechowuje odpowiedzi, w tym wyodrębnione wartości z syntetycznych dokumentów; logi przechowują tylko metadane zapytań. Nie publikuj katalogów `cache/`, `logs/` ani plików kluczy.

## Konfiguracja i testy

| Zmienna | Znaczenie |
|---|---|
| `DATA_DIR` | Katalog pakietu; do samodzielnej próby `tests/fixtures` |
| `ORNITH_BASE_URL` | Jeden serwer; lokalnie domyślnie `http://localhost:11434/v1` |
| `ORNITH_BASE_URLS` | Adresy serwerów rozdzielone przecinkami; mają pierwszeństwo nad pojedynczym adresem |
| `ORNITH_MODEL` | Domyślnie `ornith-1.5-9b`; dla Ollama ustaw `ornith-1.5:9b` |
| `ORNITH_API_KEY`, `ORNITH_API_KEY_FILE` | Klucz w środowisku albo ścieżka do pliku; środowisko ma pierwszeństwo |
| `ORNITH_MAX_CONCURRENCY_PER_SERVER` | Domyślnie 4; wspólny limit na model wynosi 6 |
| `QWEN_BASE_URL`, `QWEN_MODEL`, `QWEN_API_KEY` | Model zapasowy; domyślna nazwa `umed-qwen`, klucz opcjonalny |
| `CACHE_DIR`, `LOG_DIR` | Domyślnie `cache/` i `logs/` w katalogu aplikacji |

`.env.example` jest wzorem konfiguracji; aplikacja nie wczytuje automatycznie pliku `.env`. Szczegółowe polecenia Docker i prewarm są w [README_app.md](README_app.md). Adresy sieci zajęć są domyślną konfiguracją wyłącznie w `run_docker.sh`.

```bash
python -m pytest
python prewarm_cache.py --dry-run
```

Testy używają mocków lub lokalnego serwera testowego. Nie wywołują rzeczywistych modeli. Pełny pakiet jest opcjonalny dla testów; fixture ma własny słownik, reguły, schemat i dokumenty. Wynik wykonanej weryfikacji: [WERYFIKACJA.md](WERYFIKACJA.md).

## Ograniczenia

Cache i limitowanie są współdzielone między sesjami jednego procesu aplikacji. Dodatkowy proces prewarm ma własne limity, dlatego uruchom go przed zajęciami. Sesja użytkownika nie przetrwa restartu; pobierz wyniki CSV. Cache przetrwa restart, jeśli jego katalog jest zachowany. Zmiana serwera przy tej samej nazwie modelu nie zmienia klucza cache; po podmianie wag modelu użyj nowej nazwy lub osobnego `CACHE_DIR`.

Porównanie zgłoszeń opiera się na parze ID–zmienna. Powtórzone ID mogą dopasować kilka wpisów klucza; wynik nie rozstrzyga numeru wiersza. Czułość dla podzbioru wierszy nadal używa całego klucza jako mianownika. Wyniki lokalnych testów nie ustalają gotowości klinicznej ani gotowości manuskryptu.

Licencja [MIT](LICENSE), Konrad Stawiski, 2026.

## English summary

Laboratorium danych is a Polish teaching app for clinicians learning data hygiene. It reads scenario metadata, validation rules and extraction prompts from a synthetic data package. It supports local OpenAI-compatible models, multiple inference servers, persistent result caching and instructor prewarming. Included data are entirely synthetic. This is an educational tool, not a medical device.
