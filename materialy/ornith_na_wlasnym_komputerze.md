# Ornith-1.5-9B na własnym komputerze

## Czym jest model Ornith-1.5-9B?
Ornith-1.5-9B to otwarty model językowy ogólnego przeznaczenia o 9 mld parametrów, zbudowany na modelu Qwen3.5 (strona modelu: huggingface.co/ornith-ai/Ornith-1.5-9B). Nie jest to model medyczny i nie był trenowany specjalnie na dokumentacji klinicznej. Udostępniono go na licencji MIT, która pozwala na bezpłatne użycie, także w nauce i dydaktyce. Na zajęciach używaliśmy tego samego pliku, który możesz zainstalować u siebie.

Aplikacja „Laboratorium danych” wykorzystywana podczas dzisiejszych ćwiczeń jest dostępna publicznie w serwisie GitHub pod adresem: `kstawiski/laboratorium-danych`.

---

## Wariant 1: LM Studio (najprostszy interfejs graficzny)
LM Studio działa na Windows, macOS i Linux. Pozwala rozmawiać z modelem w oknie czatu bez wiersza poleceń, a w zakładce serwera udostępnia lokalne API (adres http://localhost:1234/v1).

1. Pobierz i zainstaluj darmowy program ze strony oficjalnej: `lmstudio.ai`.
2. Uruchom program i w pasku wyszukiwania (ikona lupy) wpisz:
   `ornith-ai/Ornith-1.5-9B-GGUF`
3. Na liście dostępnych plików wybierz wersję o kwantyzacji:
   `Q4_K_M`
4. Rozmiar pobieranego pliku wynosi około 5,8 GB.
5. Wymagania sprzętowe: komputer stacjonarny lub laptop wyposażony w co najmniej 16 GB pamięci RAM.
6. Po zakończeniu pobierania przejdź do zakładki czatu (ikona dymków), wybierz załadowanie pobranego modelu do pamięci u góry ekranu i rozpocznij pracę.

---

## Wariant 2: Ollama (szybkie uruchomienie w terminalu)
Ollama to narzędzie uruchamiane z wiersza poleceń. Przydaje się do skryptów i do połączenia z aplikacją przez lokalne API (adres http://localhost:11434/v1).

1. Pobierz i zainstaluj środowisko ze strony: `ollama.com`.
2. Otwórz terminal (macOS/Linux) lub PowerShell (Windows).
3. Wpisz i uruchom następujące polecenie:
   ```bash
   ollama run ornith-1.5:9b
   ```
4. Program pobierze model (kilka GB) i otworzy rozmowę w konsoli.

---

## Wariant 3: Komputery Apple Silicon (macOS, układ Apple M)
Na komputerach Apple z procesorami M1–M4 można użyć wersji w formacie MLX, przygotowanej dla tych procesorów. LM Studio na macOS potrafi ją pobrać i uruchomić.

- Dedykowane repozytorium modelu w formacie MLX:
  `ornith-ai/Ornith-1.5-9B-MLX-4bit`
- To wersja 4-bitowa, więc zajmuje mniej pamięci niż pełny model.

---

## Zasady bezpiecznej pracy z danymi medycznymi
1. **Prawdziwe dane tylko lokalnie:** Prawdziwe dane pacjentów przetwarzaj modelem lokalnym, na sprzęcie i zasadach zatwierdzonych przez instytucję. Nie wklejaj ich do publicznych czatów ani usług w chmurze.
2. **Zgoda instytucji:** Praca na rzeczywistych danych pacjentów wymaga zgody instytucji, a gdy dotyczy to badania naukowego, także spełnienia wymagań komisji bioetycznej i inspektora ochrony danych.
3. **Bezwzględna weryfikacja wyników:** Odpowiedzi i zestawienia generowane przez sztuczną inteligencję zawsze podlegają krytycznej ocenie lekarza. Modele językowe mogą generować błędy, halucynacje lub pomijać istotne szczegóły kliniczne. Model AI stanowi wyłącznie narzędzie wspomagające, a odpowiedzialność za decyzje medyczne spoczywa na człowieku.
