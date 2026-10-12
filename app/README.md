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
| `ORNITH_LABEL`, `QWEN_LABEL` | Nazwy modeli w panelu; domyślnie `Ornith` i `Qwen` |
| `ORNITH_REASONING_EFFORT`, `QWEN_REASONING_EFFORT` | Wartość parametru `reasoning_effort`; bez ustawienia parametr nie jest wysyłany. Dla Gemma 4 w Gemini API ustaw `minimal` |
| `OLLAMA_BASE_URL` | Opcjonalny adres Ollama bez `/v1`, np. `http://localhost:11434`; lista modeli z `/api/tags`, zapasowo `/v1/models`, cache 30 s |
| `ALLOW_CUSTOM_ENDPOINT` | Domyślnie wyłączone. `1` udostępnia adres, klucz i nazwę własnego modelu w panelu |
| `CACHE_DIR`, `LOG_DIR` | Domyślnie `cache/` i `logs/` w katalogu aplikacji |

`.env.example` jest wzorem konfiguracji; aplikacja nie wczytuje automatycznie pliku `.env`. Docker z Ollama opisano poniżej; prewarm: `python prewarm_cache.py --dry-run`. Adresy sieci zajęć są domyślną konfiguracją wyłącznie w `run_docker.sh`.

```bash
python -m pytest
python prewarm_cache.py --dry-run
```

Testy używają mocków lub lokalnego serwera testowego. Nie wywołują rzeczywistych modeli. Pełny pakiet jest opcjonalny dla testów; fixture ma własny słownik, reguły, schemat i dokumenty. Wynik wykonanej weryfikacji: [WERYFIKACJA.md](WERYFIKACJA.md).

## Samodzielna instalacja z Ollama

W katalogu `app/` uruchom:

```bash
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5:7b
```

Otwórz `http://localhost:8501`. W panelu wybierz `Ollama: qwen2.5:7b`. Lista odświeża się przy kolejnym działaniu w aplikacji, najpóźniej po wygaśnięciu cache 30 s. Możesz pobrać także `gemma3:4b` lub `gemma3:12b` tym samym poleceniem. To propozycje modeli 4–12 B do lokalnych ćwiczeń; poprawność JSON i treści zależy od modelu oraz polecenia. [Qwen2.5](https://ollama.com/library/qwen2.5) opisuje obsługę strukturalnych wyników JSON; [Gemma 3](https://ollama.com/library/gemma3) udostępnia warianty 4 B i 12 B. Nie wykonywano tu oceny jakości tych modeli.

Compose buduje aplikację, montuje `${DATA_DIR:-../exercises/dane}` tylko do odczytu i przechowuje modele Ollama w nazwanym wolumenie. Do próby z fixture użyj `DATA_DIR=./tests/fixtures docker compose up -d --build`. Cache i logi aplikacji mają osobne wolumeny. Port aplikacji jest dostępny na tym komputerze; Ollama działa w sieci Compose. Opcjonalna sekcja GPU NVIDIA jest zakomentowana w `docker-compose.yml`.

Bez Dockera zainstaluj Ollama natywnie, uruchom jej serwer, pobierz model i ustaw zmienne w aktywnym środowisku Python:

```bash
ollama pull qwen2.5:7b
export OLLAMA_BASE_URL=http://localhost:11434
export DATA_DIR=tests/fixtures
pip install -r requirements.txt
streamlit run app.py
```

W PowerShell użyj `$env:OLLAMA_BASE_URL="http://localhost:11434"` i `$env:DATA_DIR="tests/fixtures"`. Modele z `ORNITH_*` i `QWEN_*` pozostają dostępne obok modeli Ollama. Brak połączenia z Ollama wyświetla informację i nie blokuje pozostałych serwerów. Odpowiedź HTTP 429 powoduje oczekiwanie według `Retry-After` lub rosnącego odstępu od 5 s, w ramach wspólnego limitu 180 s. Błąd połączenia nadal pozwala na jedną próbę na innym skonfigurowanym serwerze.

`ALLOW_CUSTOM_ENDPOINT=1` włącza panel „Własny serwer modelu”. Podaj adres OpenAI API (np. `http://localhost:1234/v1`), opcjonalny klucz i nazwę modelu. Przycisk pobiera listę modeli; wybór potwierdź przyciskiem „Użyj wybranego modelu”. Klucz pozostaje wyłącznie w `st.session_state`, bez logowania i zapisu do cache lub plików. Ten panel jest domyślnie wyłączony: na serwerze publicznym umożliwiałby każdemu użytkownikowi wywoływanie dowolnych adresów z serwera aplikacji. Compose włącza go dla samodzielnej instalacji; przed udostępnieniem publicznym ustaw `ALLOW_CUSTOM_ENDPOINT: "0"`.

## Własne reguły i materiały

Reguły tworzą listę wierszy do sprawdzenia. Nie usuwają ani nie włączają lub wykluczają pacjentów. Zaznaczanie wszystkich reguł działa globalnie i w każdej kategorii. Własne wyrażenie może opisywać błąd albo poprawną wartość; drugi wariant jest negowany. Podgląd pokazuje liczbę oznaczonych wierszy oraz pierwszych 10 z użytymi zmiennymi. Własne wyrażenia pomijają wiersze z brakiem w dowolnej użytej zmiennej, również po negacji. Kontrola zakresu pomija braki i nieczytelne liczby. Braki sprawdzaj osobną regułą. Podsumowanie pokazuje wiersze i pacjentów dla każdej uruchomionej reguły. Własne reguły można pobrać i importować jako listę JSON (`range`, `category`, `query`); import waliduje każdą pozycję i zgłasza odrzucone reguły.

W ekstrakcji edytuj JSON, następnie kliknij „Zastosuj schemat”. Model używa zastosowanego schematu, nie niezapisanej treści edytora. Obsługiwane słowa walidacyjne: `type`, `properties`, `required`, `additionalProperties` (true/false), `items`, `maxItems`, `anyOf`, `enum`, `minimum`, `maximum`, `pattern`, `format` (tylko `date`). `$schema`, `title` i `description` są opisami i nie ustanawiają ograniczeń wartości. Tabela pokazuje pola zastosowanego schematu. Domyślny schemat można przywrócić lub pobrać.

Dodaj najwyżej 20 syntetycznych dokumentów `.txt` / `.md` po 100 kB, zapisanych jako UTF-8, lub wklej tekst. Własne dokumenty mają oznaczenie „(własny)”, są przechowywane tylko w sesji i nie są oceniane z kluczem. Dokładność obejmuje wyłącznie dokumenty pakietu oraz pola wspólne schematu i klucza; pozostałe wyniki są wyświetlane bez punktacji. Przy braku dokumentów lub schematu pakietu można zacząć od minimalnego przykładu i własnego tekstu.

Panel pozwala wgrać syntetyczny rejestr (do 10 MB i 10 000 wierszy) oraz własny słownik CSV/XLSX (do 5 MB). Słownik wymaga `zmienna` i `typ`, a opcjonalne kolumny uzupełnia pustymi wartościami. Pobierz wzór słownika z panelu. Własny słownik wyznacza domyślne reguły i trafia do poleceń AI. Reguły wymagające brakujących kolumn są pomijane z jedną informacją. Klucz błędów pakietu nie dotyczy własnego rejestru ani słownika. Ekspander „Co dokładnie dostaje model” pokazuje wiadomości systemowe i pierwszą wybraną paczkę w kontroli wiarygodności klinicznej.

Wgrane dane i własne dokumenty nie są zapisywane na dysku. Wywołania z własnym rejestrem, słownikiem lub dokumentem oraz wywołania własnego serwera pomijają odczyt i zapis trwałego cache. Logi zachowują tylko metadane. Pobierane wyniki mogą zawierać wyodrębniony syntetyczny tekst.

## Ograniczenia

Cache i limitowanie są współdzielone między sesjami jednego procesu aplikacji. Dodatkowy proces prewarm ma własne limity, dlatego uruchom go przed zajęciami. Sesja użytkownika nie przetrwa restartu; pobierz wyniki CSV. Cache przetrwa restart, jeśli jego katalog jest zachowany. Zmiana serwera przy tej samej nazwie modelu nie zmienia klucza cache; po podmianie wag modelu użyj nowej nazwy lub osobnego `CACHE_DIR`.

Porównanie zgłoszeń opiera się na parze ID–zmienna. Powtórzone ID mogą dopasować kilka wpisów klucza; wynik nie rozstrzyga numeru wiersza. Czułość dla podzbioru wierszy nadal używa całego klucza jako mianownika. Wyniki lokalnych testów nie ustalają gotowości klinicznej ani gotowości manuskryptu.

Licencja [MIT](LICENSE), Konrad Stawiski, 2026.

## English summary

Laboratorium danych is a Polish teaching app for clinicians learning data hygiene. It reads scenario metadata, validation rules and extraction prompts from a synthetic data package. It supports local OpenAI-compatible models, multiple inference servers, persistent result caching and instructor prewarming. Included data are entirely synthetic. This is an educational tool, not a medical device.
