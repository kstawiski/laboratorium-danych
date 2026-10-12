# Laboratorium danych

Aplikacja do ćwiczeń z higieny danych dla lekarzy. Działa na Twoim komputerze. Pomaga sprawdzać rejestr, tworzyć reguły, wyodrębniać dane z dokumentów i porównywać wyniki z kluczem ćwiczeń. Autor: Konrad Stawiski, Uniwersytet Medyczny w Łodzi, 2026.

Wszystkie dołączone dane są syntetyczne. Nie wgrywaj prawdziwych danych pacjentów. Wyniki AI sprawdzaj w źródle. Aplikacja służy do nauki; nie jest wyrobem medycznym.

## Jak zacząć

1. Zainstaluj [Ollama](https://ollama.com/download) i uruchom ją. To darmowy program, który uruchamia modele AI na Twoim komputerze.
2. Pobierz instalator Laboratorium danych dla swojego systemu ze strony [Releases](https://github.com/kstawiski/laboratorium-danych/releases) i zainstaluj aplikację (szczegóły poniżej).
3. Otwórz Laboratorium danych. Aplikacja sama wykryje Ollamę i poleci model dopasowany do pamięci komputera. Kliknij „Pobierz” i poczekaj na koniec pobierania.

Nie potrzebujesz terminala, Pythona ani ręcznej konfiguracji. Przy co najmniej 16 GB RAM aplikacja poleca Gemma 4 12B (około 8 GB do pobrania), przy mniejszej pamięci Gemma 4 E4B (około 6,6 GB; potrzeba co najmniej 12 GB RAM). Na słabszym komputerze możesz zamiast tego wpisać własny bezpłatny klucz Google w panelu „Model AI”. Wtedy dane opuszczają komputer, więc używaj wyłącznie danych syntetycznych.

### Instalacja

- **Windows:** otwórz pobrany instalator `.exe`. Instaluje aplikację dla Twojego konta, bez uprawnień administratora. Potem otwórz „Laboratorium danych” z pulpitu lub menu Start. Wariant ZIP: rozpakuj cały folder i otwórz `laboratorium-danych.exe`.
- **macOS:** wybierz plik DMG `arm64` dla komputerów z procesorem Apple (M1 i nowsze) albo `x64` dla Intela. Otwórz DMG, przeciągnij aplikację do folderu Aplikacje i otwórz ją dwukrotnym kliknięciem.
- **Linux:** pobierz AppImage, w jego właściwościach zezwól na uruchamianie jako programu i otwórz dwukrotnym kliknięciem. W części dystrybucji potrzebny jest składnik FUSE.

Pakiety nie mają podpisu wydawcy, więc przy pierwszym uruchomieniu system wyświetli ostrzeżenie. Windows (SmartScreen): wybierz **„Więcej informacji” → „Uruchom mimo to”**. macOS: po pierwszej próbie otwórz **Ustawienia systemowe → Prywatność i ochrona → „Otwórz mimo to”**.

### Co aplikacja zapamiętuje

Ustawienia modelu i klucze są zapisywane lokalnie, w folderze użytkownika. Wgrane pliki, wyniki, własne dokumenty i własne reguły istnieją tylko do zamknięcia aplikacji, więc przed zamknięciem pobierz wyniki i wyeksportuj reguły. Folder z ustawieniami, pamięcią podręczną i dziennikiem otworzysz z menu **„Laboratorium danych” → „Folder z danymi i ustawieniami”**:

- Windows: `%APPDATA%\Laboratorium danych`
- macOS: `~/Library/Application Support/Laboratorium danych`
- Linux: `~/.config/Laboratorium danych`

Przy zgłaszaniu problemu dołącz plik `logs/serwer.log` z tego folderu.

## Serwer na czas zajęć

Podczas zajęć prowadzący uruchamia [serwer ćwiczeń](https://cwiczenia.konsta.com.pl). Otwórz stronę, wpisz nazwę grupy i wybierz model dostępny na zajęciach. Poza zajęciami serwer może być wyłączony. Ustawienia i własny klucz Google na serwerze pozostają wyłącznie w sesji.

## Dla programistów

Kod Streamlit jest w `app/`. Instrukcje uruchomienia ze źródeł, testy i opis funkcji są w [app/README.md](app/README.md). Zwykłe uruchomienie aplikacji działa w trybie lokalnym i udostępnia ustawienia modeli w interfejsie.

Pakiet [PROSTATA-RT](exercises/README_dane.md) zawiera 120 syntetycznych rekordów, 56 celowych błędów, 5 rzadkich poprawnych wartości i 60 dokumentów z kluczem. Katalog `materialy/` zawiera instrukcje ćwiczeń. Pakiet desktopowy jest budowany osobno; lokalne zmiany kodu nie aktualizują wydanego instalatora.

## Dla administratorów

Zmienne środowiskowe służą administratorom i launcherowi. Uczestnicy nie muszą ich ustawiać. `LAB_PUBLIC_SERVER=1` włącza tryb serwera zajęć: modele operatora oraz opcjonalny własny klucz Google, bez Ollama i bez własnych adresów URL. Adresy modeli operatora trzeba ustawić jawnie. Bez tego nie pojawiają się na liście.

Docker Compose z osobnym kontenerem Ollama, trwałe katalogi, zmienne modeli i prewarm opisano w [instrukcji aplikacji](app/README.md#dla-administratorów). Nie publikuj plików ustawień, kluczy, cache ani logów.

Licencja MIT.
