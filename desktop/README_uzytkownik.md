## Wersja na komputer (bez instalowania Pythona)

Pobierz plik dla swojego systemu z [Releases](https://github.com/kstawiski/laboratorium-danych/releases).

- **Windows:** otwórz instalator `win-x64-setup.exe`. Instaluje aplikację dla Twojego konta, bez uprawnień administratora. Potem otwórz „Laboratorium danych” z pulpitu lub menu Start. Wariant ZIP: rozpakuj cały folder i otwórz `laboratorium-danych.exe`.
- **macOS:** wybierz DMG `arm64` dla Apple Silicon albo `x64` dla Intela. Otwórz DMG, przeciągnij aplikację do folderu Aplikacje i otwórz ją dwukrotnym kliknięciem.
- **Linux:** pobierz AppImage, w jego właściwościach zezwól na uruchamianie jako programu i otwórz dwukrotnym kliknięciem. System musi obsługiwać AppImage; w części dystrybucji potrzebny jest składnik FUSE.

Pakiety nie mają podpisu wydawcy. Windows może wyświetlić SmartScreen: wybierz **„Więcej informacji” → „Uruchom mimo to”**. Na macOS, po pierwszej próbie uruchomienia, otwórz **Ustawienia systemowe → Prywatność i ochrona → „Otwórz mimo to”**. macOS wymaga też zatwierdzenia komunikatu przy ponownym otwarciu.

Aplikacja otwiera własne okno. Python jest dołączony. Nie trzeba otwierać terminala ani ustawiać zmiennych środowiskowych.

Dołączony pakiet ćwiczeń zawiera dane syntetyczne. Logi, pamięć podręczna i miejsce na ustawienia znajdują się w folderze użytkownika. Otwórz go z menu **„Laboratorium danych” → „Folder z danymi i ustawieniami”**:

- Windows: `%APPDATA%\Laboratorium danych`
- macOS: `~/Library/Application Support/Laboratorium danych`
- Linux: `~/.config/Laboratorium danych` (albo katalog określony przez system)

Pliki pobrane z aplikacji zapisuj w wybranym folderze. Wgrywane dane i bieżąca sesja nie są automatycznie zachowywane po zamknięciu; pobierz potrzebne wyniki. Dołączone ćwiczenia pozostają w instalacji. Przy zgłaszaniu problemu plik dziennika to `logs/serwer.log` w folderze użytkownika.

Lokalne AI wymaga osobnej instalacji [Ollama](https://ollama.com/download) i pobrania modelu w Ollama. Gdy Ollama działa na tym komputerze, aplikacja sama wykrywa listę dostępnych modeli. Python i Ollama to osobne składniki; instalator aplikacji nie zawiera modeli AI.
