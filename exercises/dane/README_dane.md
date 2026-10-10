# PROSTATA-RT — dane do ćwiczeń

120 fikcyjnych mężczyzn leczonych radykalną RT ± ADT. Nie importowano danych pacjentów. Nazwiska mają człon „Fikcyjny”; wszystkie numery PESEL mają celowo błędną cyfrę kontrolną. Materiał służy ćwiczeniu higieny danych. Lokalne generowanie i testy nie stanowią oceny gotowości klinicznej ani publikacyjnej.

## Odtworzenie

W katalogu `exercises/`:

```bash
/home/linuxbrew/.linuxbrew/bin/python3 -B generator/generuj_dane.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 /home/linuxbrew/.linuxbrew/bin/python3 -B -m pytest generator/test_spojnosc.py -q -p no:cacheprovider
/home/linuxbrew/.linuxbrew/bin/python3 -B walidacja/waliduj.py dane/rejestr_brudny.xlsx
```

Generator: stały seed 20261011, biblioteka standardowa, pandas, numpy, openpyxl. Walidator odczytuje `dane/reguly.yaml` przez PyYAML. Katalog reguł jest także skopiowany do `walidacja/reguly.yaml`. Pytest jest potrzebny do testów. Bez pobierania danych i połączeń sieciowych. Ścieżki wyników są względne wobec kodu, niezależne od katalogu uruchomienia. Wszystkie własne wyniki są nadpisywane. CSV, TXT, JSON, YAML, ZIP i XLSX są deterministyczne w użytych wersjach bibliotek; czasy ZIP/XLSX są unormowane.

## Pliki

- `dane/rejestr_czysty.csv`: 120 rekordów prawdy, 34 zmienne; BCR 15/120 (12.5%), zgony 5.
- `dane/rejestr_brudny.csv` i `.xlsx`: 121 rekordów, wraz z dodatkowym duplikatem; CSV ze średnikiem, UTF-8 z BOM. Jedyna zakładka XLSX: `dane`.
- `dane/slownik_danych.csv` i `.xlsx`: nazwy, typy, jednostki, zakresy, kody braków i definicje protokołu.
- `dane/klucz_bledow.csv` i `.xlsx`: jeden wpis na zmienioną komórkę oraz jeden na dodatkowy rekord; numer wiersza Excel uwzględnia nagłówek.
- `dane/pulapki_nie_bledy.csv`: pięć prawdziwych, rzadkich wartości.
- `dane/karta_znalezisk.xlsx`: pusty formularz dla grupy.
- `dane/dokumenty/DOK-01.txt`…`DOK-60.txt` i `dane/dokumenty.zip`: 60 dokumentów dla PR-061…PR-120, 150–400 słów każdy, trzy rodzaje dokumentacji, sześć układów i odrębne narracje.
- `dane/ekstrakcja_schemat.json`: 25 pól, brak lub nierozstrzygnięta sprzeczność jako null.
- `dane/ekstrakcja_prompt.txt`: instrukcja ekstrakcji, jednostki i rozstrzyganie sprzeczności.
- `dane/ekstrakcja_klucz.csv`, `ekstrakcja_trudnosci.csv`, `ekstrakcja_dowody.csv`: standard odniesienia, trudności i dosłowne fragmenty źródła z zasadą przeliczenia.
- `dane/reguly.yaml`: id, opis, typ, zmienne, wyrażenie pandas lub zakres; kontrole wielopolowe mają parametry i identyfikator `kontrola` używany przez walidator.
- `dane/scenariusz.json`: opis i jawne definicje protokołu.
- `dane/wyniki_referencyjne/`: raport naruszeń, pokrycie klucza i podsumowanie liczbowe.
- `dane/manifest_sha256.csv`: sumy kontrolne wszystkich pozostałych plików w `dane/`.
- `generator/generuj_dane.py`, `generator/test_spojnosc.py`, `walidacja/waliduj.py`: kod i testy.
- `_archiwum_kardioonko/`: zachowany poprzedni pakiet, wraz z kodem, dokumentami i wynikami. Nie stanowi wejścia bieżącego ćwiczenia.

## Definicje i odczyt dokumentów

Gleason jest sumą wzorców. ISUP: 3+3→1, 3+4→2, 4+3→3, suma 8→4, suma 9–10→5. W uproszczonej grupie ryzyka warunki wysokiego ryzyka mają pierwszeństwo: PSA >20, ISUP 4–5, cT2c–cT4 lub cN1. Niskie: PSA <10, ISUP 1, cT1c–cT2a i cN0; pozostałe: pośrednie. To definicja ćwiczeniowa, nie pełna klasyfikacja EAU. M1 nie jest uwzględnione; v2 nie wskazuje konkretnej pułapki M1 ani kolumny M.

Phoenix: ostatnie PSA **≥ nadir + 2 ng/ml**, z granicą włączoną. SBRT ⇔ 5 frakcji. Dopuszczalne dawki i frakcje: 78/39, 76/38, 60/20, 62/20, 70/28, 36,25/5 i 40/5. Dawka dotyczy prostaty. ADT=0 wymaga zerowego czasu ADT; czas w rejestrze jest całkowitym planem, a nie czasem do oznaczenia testosteronu. Typowe czasy ADT w protokole: 6 mies. w pośrednim niekorzystnym i 18–36 mies. w wysokim ryzyku.

Kreatynina µmol/l ÷88,4 → mg/dl; Hb mmol/l ÷0,6206 → g/dl, obie do dwóch miejsc. Testosteron nmol/l ×28,84 → ng/dl. Bez jawnej jednostki nie przeliczać na podstawie samego wyniku. Zapisy dat z ukośnikiem **w dokumentach** oznaczają DD/MM/RRRR; brudny rejestr nie ma tej deklaracji. Numer seryjny Excela wymaga potwierdzenia systemu dat. Tekst „kwiecień 2025” nie podaje dnia.

Brak informacji o NT, DM lub paleniu to null. „Nie pali od 10 lat” oznacza former. CTCAE w kluczu jest maksimum całej obserwacji. Konsultacje kwalifikacyjne mają wyraźnie oddzielone późniejsze uzupełnienie wyników. W DOK-14 potwierdzona data urodzenia ma pierwszeństwo przed wiekiem ze skierowania. W DOK-16 aneks potwierdza ISUP 3 i koryguje ISUP 2. W DOK-17 sprzeczność ISUP bez aneksu daje null. W DOK-19 dwie nierozstrzygnięte daty urodzenia dają null. W DOK-18 PSA <0,01 bez wyniku punktowego i wynik Phoenix mają null. Puste pola klucza CSV odpowiadają null w JSON; PESEL nie jest źródłem danych do ekstrakcji.

## Błędy i pułapki

56 błędów: 55 zmienionych komórek oraz jeden dodatkowy pełny duplikat PR-076 pod ID PR-121. Dodatkowy wiersz liczymy jako jeden błąd rekordu, nie 33 błędy poszczególnych wartości. W kluczu ma pustą wartość prawdziwą ID; po potwierdzeniu należy usunąć dodatkowy rekord. Brudnego i czystego rejestru nie łączyć wyłącznie po ID: identyfikatory zmieniono i powielono. Numer wiersza Excel przestaje być stabilny po sortowaniu pliku.

Rozmieszczenie ma stały seed 20261013. Liczby błędów w kolejnych blokach 20 pacjentów: 1–20: 11; 21–40: 8; 41–60: 10; 61–80: 8; 81–100: 7; 101–120: 11. To 55 zmienionych komórek w PR-001…PR-120; dodatkowy duplikat jest wierszem 121 danych (122 w Excelu). Każdy pacjent ma najwyżej jeden wstrzyknięty błąd. Pięć pułapek leży w pięciu różnych blokach, w wierszach bez błędów. Wariant „pr 014”, źródło pełnego duplikatu PR-076 oraz prawda histopatologiczna PR-116 i PR-117 zachowują pozycje; pozostałe przykłady są losowane wraz z odpowiadającą im prawdą.

Kontrakt v2 podaje orientacyjnie 36–42, ale jego pełna lista wymaga co najmniej 56 osobnych błędów. Przyjęto pełne pokrycie: wszystkie wymienione warianty faktycznie występują w brudnym rejestrze i kluczu, co sprawdza test. Nie przeniesiono brakujących wariantów wyłącznie do testów.

| Kategoria | Liczba |
| --- | ---: |
| brak_danych | 6 |
| duplikat | 2 |
| format_daty | 6 |
| identyfikator | 2 |
| jednostka | 7 |
| kategoria | 6 |
| kodowanie | 4 |
| liczba_jako_tekst | 4 |
| logika_czasowa | 3 |
| prywatnosc | 2 |
| spojnosc_pol | 8 |
| struktura | 2 |
| zakres | 4 |
| Razem | 56 |

Pułapki (reguły i klucz nie zgłaszają tych rekordów jako błędnych):

- PR-058: SBRT 36,25 Gy/5 fr., czyli 7,25 Gy/fr.; schemat dopuszczony protokołem.
- PR-090: Wiek dokładnie 89 lat przy RT 2021-04-03; nie usuwać jako odstającego.
- PR-075: PSA 148 ng/ml przy cN1; wysokie, ale możliwe; grupa wysokiego ryzyka.
- PR-003: Udokumentowane zatrzymanie moczu wymagające cewnikowania podczas RT; prawdziwy odczyn G3.
- PR-030: Pomiar 12 dni po pierwszym podaniu agonisty LHRH, w pierwszym miesiącu ADT; jednostka ng/dl potwierdzona w notes.

## Wynik walidacji i ograniczenia

Reguły: 79 naruszeń, 63 różnych komórek, 56/56 trafień w klucz. Jedna komórka może naruszać kilka reguł. Dodatkowo wskazane poprawne pola należą do sprzecznych par lub powtarzającego się ID; walidator nie zna prawdy i nie rozstrzyga, który element pary jest błędny. Pokrycie klucza nie oznacza takiej samej skuteczności na innych danych.

Wyrażenia agregatowe YAML pokazują przykładową kontrolę; pełny walidator stosuje `kontrola`, wszystkie `zmienne`, parametry i słownik. Aplikacja wykonująca wyłącznie wyrażenia musi uwzględnić to rozszerzenie dla pełnej zgodności. Nie testowano aplikacji z części B ani modelu językowego. Testy dokumentów odczytują jawne fakty niezależnie od generatora i sprawdzają cytowane fragmenty, przeliczenia, negacje oraz null; nie stanowią pełnego audytu medycznego. Opcjonalnej implementacji R nie przygotowano.

Do pracy grupowej udostępnić brudny rejestr, słownik, dokumenty i kartę znalezisk. Czysty rejestr, klucze i wyniki referencyjne odsłonić podczas omówienia.
