# Laboratorium danych

Aplikacja do ćwiczeń z higieny danych dla lekarzy. Domyślnie działa na Twoim komputerze, z modelem w Ollama. Wszystkie dołączone dane są syntetyczne. Nie wklejaj ani nie wgrywaj prawdziwych danych pacjentów. Wynik AI wymaga sprawdzenia źródła.

## Jak zacząć

1. Zainstaluj [Ollama](https://ollama.com/download) i otwórz program.
2. Zainstaluj Laboratorium danych z Releases repozytorium. Instrukcja wersji na komputer znajduje się w [głównym README](../README.md#jak-zacząć).
3. Otwórz aplikację. W zakładce Start kliknij „Pobierz” przy polecanym modelu. Po zakończeniu pobierania aplikacja wybierze model automatycznie.

Panel „Model AI” po lewej pozwala sprawdzić połączenie i wybrać sposób pracy:

- **Ollama na tym komputerze.** Aplikacja wykrywa uruchomioną Ollama i pokazuje pobrane modele z rozmiarami. „Sprawdź ponownie” odświeża listę. Modele pobierasz przyciskiem „Pobierz”; pasek pokazuje postęp i rozmiar pobrania.
- **Google Gemini (bezpłatny klucz).** Otwórz [Google AI Studio](https://aistudio.google.com/apikey), zaloguj się, utwórz klucz i wklej go do pola hasła. Wybierz model i sprawdź połączenie. Dane opuszczają komputer, więc używaj tylko danych syntetycznych. Dostępność i limity usługi zależą od konta Google.
- **Inny serwer zgodny z OpenAI (zaawansowane).** W lokalnej aplikacji podaj adres serwera i opcjonalny klucz. Pobierz listę modeli, wybierz model i sprawdź połączenie.

Lista „Model” obejmuje wykryte modele Ollama, jawnie skonfigurowane modele operatora oraz modele Google i własnego serwera, które przeszły sprawdzenie połączenia. Dostępność serwera może później się zmienić; przycisk „Sprawdź połączenie” pozwala to zweryfikować. Zmiana adresu lub klucza wymaga ponownego sprawdzenia modeli tego dostawcy.

Na tym komputerze ustawienia modelu, klucze i ostatni wybór są zapisane w `ustawienia.json` w katalogu danych użytkownika. Lokalizacja jest widoczna w zwiniętym panelu „Informacje techniczne”. Klucze są zapisane w tym lokalnym pliku; nie udostępniaj go. Na systemach POSIX aplikacja nadaje plikowi uprawnienia 0600. Ustawienia nie wymagają zmiennych środowiskowych ani terminala.

Wgrane pliki, własne dokumenty, własne reguły i wyniki pozostają w sesji. Pobierz wyniki i wyeksportuj reguły przed jej zamknięciem. Cache pakietu może przetrwać restart; nie zastępuje eksportu wyników.

## Polecane modele lokalne

Rekomendacja zależy od całkowitej pamięci RAM: około 16 GB lub więcej → Gemma 4 12B, mniej → Gemma 4 E4B. Jeśli ilość pamięci jest nieznana, aplikacja proponuje 12B i pokazuje wymagania. E4B potrzebuje co najmniej 12 GB RAM; na słabszym komputerze można użyć Google.

| Model Ollama | Pobranie | Minimalna pamięć | Wynik kontroli klinicznej | Poprawne pola ekstrakcji |
|---|---|---|---|---|
| `gemma4:12b` | około 8,0 GB | 16 GB RAM lub GPU z 12 GB | 42/56 błędów; 16 fałszywych alarmów | 1442/1500 (96,1%) |
| `gemma4:e4b` | około 6,6 GB | 12 GB RAM | 19/56 błędów; 54 fałszywe alarmy | 1433/1500 (95,5%) |
| `ornith-1.5:9b` | około 6,6 GB | 12 GB RAM | 16/56 błędów; 27 fałszywych alarmów | 1392/1500 (92,8%) |

Źródło: próba managera z 12 października 2026 r.; jeden przebieg 72 domyślnych zapytań PROSTATA-RT na model (60 dokumentów i 12 paczek po 10 wierszy), Ollama 0.40.3, RTX 2080 Ti (11 GB). Kontrola obejmowała wiersze 1–120 i najwyżej 8 zgłoszeń na paczkę; 3 błędy w kolumnie notes nie były wysyłane do modelu. Próba używała API zgodnego z OpenAI i kontekstu 16384, a nie nowego transportu natywnego. Mediana dla 12B: 4,2 s na dokument i 10,4 s na paczkę. Bez karty graficznej może być kilka razy wolniej. Te wyniki nie ustanawiają przydatności klinicznej. Ornith nie jest wybierany jako model polecany.

## Praca na zajęciach

Serwer [cwiczenia.konsta.com.pl](https://cwiczenia.konsta.com.pl) jest uruchamiany na czas zajęć. Udostępnia modele prowadzącego i opcjonalnie własny klucz Google. Nie udostępnia Ollama ani własnych adresów serwerów. Ustawienia pozostają tylko w sesji.

Wpisz nazwę grupy i przejdź przez siedem zakładek. Kontrola kliniczna domyślnie obejmuje 20 wierszy w paczkach po 10. Ekstrakcja dokumentów działa kolejno. Klucz pojawia się po wybraniu „Pokaż klucz”.

## Dla programistów

Wymagany Python 3.12. W katalogu `app/` utwórz środowisko wirtualne, zainstaluj zależności i uruchom Streamlit:

```bash
python -m venv .venv
# Aktywuj środowisko zgodnie z systemem operacyjnym.
pip install -r requirements.txt
streamlit run app.py
```

Bez zmiennych środowiskowych działa tryb lokalny. Aplikacja szuka pakietu w `../exercises/dane`, następnie `./dane`; w uruchomieniu ze źródeł brak lub wadliwy pakiet uruchamia mały zestaw próbny z ostrzeżeniem. Desktop nie używa fixture: błąd pakietu pokazuje instrukcję ponownej instalacji.

```bash
python -m pytest -q -p no:cacheprovider
```

Testy modeli używają mocków, w tym MockTransport dla rzeczywistego SDK. Nie otwierają połączeń sieciowych ani nie wywołują rzeczywistych modeli. Polecenia i klucze cache dla dotychczasowych zapytań są zachowane.

Ollama korzysta z `POST /api/chat`: schemat w `format`, `stream: false`, `think: false`, `keep_alive: "15m"` i `options` z `num_ctx`, `temperature`, `num_predict`. Kontekst jest oszacowany z długości przygotowanego polecenia (około 3 znaki/token), limitu odpowiedzi i zapasu 1024 tokenów, zaokrąglony do wielokrotności 4096 w zakresie 8192–32768. Limit 32768 oznacza, że bardzo duże własne polecenia nadal mogą przekroczyć kontekst modelu. Timeout wynosi 600 s, a zapytania do jednej instancji Ollama są wykonywane kolejno. Pozostałe modele zachowują transport zgodny z OpenAI i obsługę 429.

Google używa stałego adresu `https://generativelanguage.googleapis.com/v1beta/openai`, modeli `gemma-4-31b-it` oraz `gemma-4-26b-a4b-it`, z `reasoning_effort="minimal"`. Zapytania z własnym kluczem Google lub własnym serwerem pomijają trwały cache. Klucze nie trafiają do kluczy cache, plików cache ani logów. Logi zawierają metadane bez treści dokumentów i odpowiedzi.

## Dla administratorów

Poniższe zmienne są przeznaczone dla administratorów i launchera. Użytkownicy konfigurują model w aplikacji.

| Zmienna | Znaczenie |
|---|---|
| `LAB_PUBLIC_SERVER` | `1` włącza serwer zajęć. Pozostałe wartości oznaczają tryb lokalny. |
| `LAB_DESKTOP` | Launcher ustawia `1`; brak pakietu nie uruchamia fixture. |
| `LAB_USER_DIR` | Katalog ustawień. Domyślnie `~/.laboratorium-danych`; na serwerze ustawienia nie są zapisywane. |
| `DATA_DIR` | Opcjonalny katalog pakietu danych. |
| `LOG_DIR`, `CACHE_DIR` | Lokalne domyślne katalogi w katalogu użytkownika; publicznie w `app/`. Launcher podaje własne katalogi. |
| `OLLAMA_BASE_URL` | Opcjonalny adres Ollama dla operatora, bez `/v1`. Domyślnie `http://127.0.0.1:11434`. Ignorowany w trybie publicznym. |
| `ORNITH_BASE_URL`, `ORNITH_BASE_URLS` | Jawny adres modelu operatora lub adresy rozdzielone przecinkami. Lista ma pierwszeństwo. Bez adresów model jest ukryty. |
| `ORNITH_MODEL` | Identyfikator modelu operatora; domyślnie `ornith-1.5-9b` po ustawieniu adresu. |
| `ORNITH_API_KEY`, `ORNITH_API_KEY_FILE` | Klucz lub plik klucza; zmienna klucza ma pierwszeństwo. |
| `ORNITH_LABEL`, `ORNITH_REASONING_EFFORT` | Etykieta i opcjonalny parametr rozumowania. |
| `ORNITH_MAX_CONCURRENCY_PER_SERVER` | Domyślnie 4; globalny limit modelu wynosi 6. |
| `QWEN_BASE_URL`, `QWEN_MODEL`, `QWEN_API_KEY`, `QWEN_API_KEY_FILE` | Drugi model operatora; ukryty bez adresu. Domyślny identyfikator po ustawieniu adresu: `umed-qwen`. |
| `QWEN_LABEL`, `QWEN_REASONING_EFFORT` | Etykieta i opcjonalny parametr rozumowania. |

`ALLOW_CUSTOM_ENDPOINT` nie jest wymagany ani odczytywany. O dostępie do własnych adresów decyduje tryb pracy. Nie uruchamiaj lokalnego trybu jako publicznego serwera: własny adres pozwala na żądania z maszyny aplikacji.

`.env.example` to wzór dla administratora, nie plik automatycznie wczytywany przez Streamlit. `run_docker.sh` przyjmuje `ENV_FILE` i jawne zmienne modeli. Do serwera zajęć ustaw `LAB_PUBLIC_SERVER=1` w konfiguracji operatora. Prewarm wymaga jawnego adresu modelu: `python prewarm_cache.py --dry-run` pokazuje zadania bez wywoływania modelu.

Docker Compose uruchamia aplikację i osobny kontener Ollama:

```bash
docker compose up -d --build
```

Otwórz `http://localhost:8501` i pobierz model w aplikacji. Compose przekazuje `OLLAMA_BASE_URL=http://ollama:11434`, montuje `${DATA_DIR:-../exercises/dane}` tylko do odczytu oraz zachowuje modele, ustawienia, cache i logi w osobnych wolumenach. Dla zestawu próbnego: `DATA_DIR=./tests/fixtures docker compose up -d --build`. Opcjonalna konfiguracja GPU NVIDIA jest zakomentowana w pliku Compose. Nie uruchomiono kontenerów w tej weryfikacji.

## Własne reguły i materiały

Reguły tworzą listę wierszy do sprawdzenia. Nie usuwają ani nie włączają lub wykluczają pacjentów. Zaznaczanie wszystkich reguł działa globalnie i w każdej kategorii. Własne wyrażenie może opisywać błąd albo poprawną wartość; drugi wariant jest negowany. Podgląd pokazuje liczbę oznaczonych wierszy oraz pierwszych 10 z użytymi zmiennymi. Własne wyrażenia pomijają wiersze z brakiem w dowolnej użytej zmiennej, również po negacji. Kontrola zakresu pomija braki i nieczytelne liczby. Braki sprawdzaj osobną regułą. Podsumowanie pokazuje wiersze i pacjentów dla każdej uruchomionej reguły. Własne reguły można pobrać i importować jako listę JSON (`range`, `category`, `query`); import waliduje każdą pozycję i zgłasza odrzucone reguły.

W ekstrakcji edytuj JSON, następnie kliknij „Zastosuj schemat”. Model używa zastosowanego schematu, nie niezapisanej treści edytora. Obsługiwane słowa walidacyjne: `type`, `properties`, `required`, `additionalProperties` (true/false), `items`, `maxItems`, `anyOf`, `enum`, `minimum`, `maximum`, `pattern`, `format` (tylko `date`). `$schema`, `title` i `description` są opisami i nie ustanawiają ograniczeń wartości. Tabela pokazuje pola zastosowanego schematu. Domyślny schemat można przywrócić lub pobrać.

Dodaj najwyżej 20 syntetycznych dokumentów `.txt` / `.md` po 100 kB, zapisanych jako UTF-8, lub wklej tekst. Własne dokumenty mają oznaczenie „(własny)”, są przechowywane tylko w sesji i nie są oceniane z kluczem. Dokładność obejmuje wyłącznie dokumenty pakietu oraz pola wspólne schematu i klucza; pozostałe wyniki są wyświetlane bez punktacji. Przy braku dokumentów lub schematu pakietu można zacząć od minimalnego przykładu i własnego tekstu.

Panel pozwala wgrać syntetyczny rejestr (do 10 MB i 10 000 wierszy) oraz własny słownik CSV/XLSX (do 5 MB). Słownik wymaga `zmienna` i `typ`, a opcjonalne kolumny uzupełnia pustymi wartościami. Pobierz wzór słownika z panelu. Własny słownik wyznacza domyślne reguły i trafia do poleceń AI. Reguły wymagające brakujących kolumn są pomijane z jedną informacją. Klucz błędów pakietu nie dotyczy własnego rejestru ani słownika. Ekspander „Co dokładnie dostaje model” pokazuje wiadomości systemowe i pierwszą wybraną paczkę w kontroli wiarygodności klinicznej.

Wgrane dane i własne dokumenty nie są zapisywane na dysku. Wywołania z własnym rejestrem, słownikiem lub dokumentem oraz wywołania własnego serwera pomijają odczyt i zapis trwałego cache. Logi zachowują tylko metadane. Pobierane wyniki mogą zawierać wyodrębniony syntetyczny tekst.

## Ograniczenia

Cache i limitowanie są współdzielone między sesjami jednego procesu aplikacji. Dodatkowy proces prewarm ma własne limity, dlatego uruchom go przed zajęciami. Sesja użytkownika nie przetrwa restartu; pobierz wyniki CSV. Cache przetrwa restart, jeśli jego katalog jest zachowany. Zmiana serwera przy tej samej nazwie modelu nie zmienia klucza cache; po podmianie wag modelu użyj nowej nazwy lub osobnego `CACHE_DIR`.

Porównanie zgłoszeń opiera się na parze ID–zmienna. Powtórzone ID mogą dopasować kilka wpisów klucza; wynik nie rozstrzyga numeru wiersza. Czułość dla podzbioru wierszy nadal używa całego klucza jako mianownika.

Licencja [MIT](LICENSE), Konrad Stawiski, 2026.

## English summary

Laboratorium danych is a Polish teaching app for clinicians learning data hygiene. It reads scenario metadata, validation rules and extraction prompts from a synthetic data package. It supports native Ollama on the user’s computer, optional OpenAI-compatible providers, in-app model settings, persistent result caching and instructor prewarming. Included data are entirely synthetic. This is an educational tool, not a medical device.
