# Instrukcja ćwiczeń: Higiena i jakość danych klinicznych w onkologii

## Informacje organizacyjne
- Prowadzący: dr n. med. Konrad Stawiski
- Odbiorcy: lekarze, uczestnicy studiów podyplomowych Uniwersytetu Medycznego w Łodzi
- Czas trwania: 120 minut
- Adres aplikacji: https://cwiczenia.konsta.com.pl
- Login: `student`
- Hasło: przekaże prowadzący na początku zajęć

## Cel ćwiczeń
Celem zajęć jest opanowanie praktycznych metod wykrywania i korygowania błędów w medycznych bazach danych. Podczas ćwiczeń wykorzystasz tradycyjny arkusz kalkulacyjny, deterministyczne reguły walidacyjne oraz lokalny model językowy sztucznej inteligencji. Nauczysz się odróżniać błędy techniczne od rzadkich sytuacji klinicznych oraz poznasz standardy przygotowania danych do analizy statystycznej.

## Zasady bezpieczeństwa danych
1. Wszystkie dane używane na zajęciach są danymi syntetycznymi. Rejestr PROSTATA-RT oraz teksty dokumentacji medycznej zostały wygenerowane sztucznie.
2. Imiona, nazwiska oraz numery identyfikacyjne są fikcyjne. Numery o strukturze PESEL mają celowo błędną cyfrę kontrolną.
3. W codziennej pracy klinicznej nigdy nie wklejaj prawdziwych danych pacjentów do publicznych narzędzi internetowych ani czatów komercyjnych.
4. Prawdziwe dane pacjentów przetwarzamy tylko w środowisku zatwierdzonym przez instytucję, na właściwej podstawie i z wymaganymi zabezpieczeniami. Na tych zajęciach rekomendujemy model lokalny.

## Organizacja pracy w zespołach
- Ćwiczenia wykonujemy w grupach 2–3-osobowych.
- Każda grupa po zalogowaniu na platformie wpisuje swoją nazwę w formacie: `Grupa X` (gdzie X to numer przypisany przez prowadzącego).
- Numer grupy wyznacza przydział dokumentów do ekstrakcji oraz zakres wierszy rejestru do audytu.

---

## Krótka ściąga funkcji arkusza kalkulacyjnego

Do sprawnej pracy z brudnym rejestrem w programach Microsoft Excel oraz LibreOffice Calc przydadzą się podstawowe mechanizmy filtrowania, sortowania i formuł logicznych.

| Zadanie | Excel i LibreOffice po polsku | Excel po angielsku |
|---|---|---|
| Filtry | Dane → Filtruj (Calc: Dane → Autofiltr) | Data → Filter |
| Sortowanie | Dane → Sortuj | Data → Sort |
| Wyróżnianie komórek | Narzędzia główne → Formatowanie warunkowe (Calc: Format → Warunkowe) | Home → Conditional Formatting |
| Czy to liczba? | `=CZY.LICZBA(A2)` | `=ISNUMBER(A2)` |
| Zbędne spacje | `=USUŃ.ZBĘDNE.ODSTĘPY(A2)` | `=TRIM(A2)` |
| Powtórzony ID | `=LICZ.JEŻELI(A:A;A2)` | `=COUNTIF(A:A,A2)` |

Wynik `CZY.LICZBA` = FAŁSZ w kolumnie liczbowej oznacza, że komórka nie zawiera liczby. Może to być liczba zapisana jako tekst (`12,4 ng/ml`), kod braku (`brak`, `nd`) albo wynik z kwalifikatorem (`<0,01`, `ok. 0,2`). Wynik `LICZ.JEŻELI` większy niż 1 oznacza powtórzony identyfikator.

### Przydatne triki:
- Separator dziesiętny: upewnij się, czy Twój system używa przecinka, czy kropki. Niezgodność separatora powoduje traktowanie liczb jako tekst.
- Apostrof przed tekstem: wpisanie znaku `'` na początku komórki wymusza format tekstowy i blokuje autokonwersję zapisu (np. zapobiega zamianie `3-4` na datę).

---

## Przebieg ćwiczeń krok po kroku

### Start (0:00–0:05): Przygotowanie stanowiska
1. Wejdź na stronę https://cwiczenia.konsta.com.pl.
2. Zaloguj się loginem `student` i hasłem podanym przez prowadzącego.
3. Wpisz nazwę swojej grupy w aplikacji.
4. Przejdź do zakładki Start i pobierz pliki robocze: `rejestr_brudny.xlsx`, `slownik_danych.xlsx` (lub `.csv`) oraz `karta_znalezisk.xlsx`.
5. Zapisz kopię roboczą pliku `rejestr_brudny.xlsx` na swoim dysku.

---

### Ćwiczenie 1: Detektyw bez AI (25 min, 0:05–0:30)
Pracujesz wyłącznie na pliku `rejestr_brudny.xlsx` bez użycia algorytmów sztucznej inteligencji. Masz przed sobą rejestr 120 chorych poddanych radioterapii z powodu raka gruczołu krokowego; plik ma 121 wierszy danych. Pracuj na kopii i nie sortuj oryginału, bo numer wiersza z oryginału posłuży do jednoznacznego wskazania rekordu.

1. Otwórz pobrany plik `rejestr_brudny.xlsx` oraz słownik danych `slownik_danych.xlsx`.
2. Przeszukaj kolumny rejestru, stosując filtry, sortowanie oraz formatowanie warunkowe.
3. Zwracaj uwagę na:
   - format identyfikatorów i obecność danych wrażliwych,
   - ukryte kody braków danych,
   - wartości liczbowe z doklejonym tekstem lub jednostką,
   - błędy autokonwersji programu Excel,
   - wartości niemożliwe biologicznie i technicznie,
   - logiczną chronologię dat,
   - spójność wzajemną powiązanych zmiennych klinicznych.
4. Każdy zidentyfikowany problem wpisz do pliku `karta_znalezisk.xlsx`.
5. W karcie znalezisk wypełnij kolumny:
   - `patient_id`: identyfikator pacjenta z danego wiersza,
   - `zmienna`: nazwa kolumny, w której występuje problem,
   - `problem`: krótki opis nieprawidłowości albo uzasadnienie decyzji,
   - `decyzja`: wybierz jedną z czterech opcji:
     * `napraw_wg_slownika`: gdy błąd jest jednoznaczny i słownik precyzuje poprawny zapis,
     * `zapytanie_do_osrodka`: gdy błąd wymaga weryfikacji w dokumentacji źródłowej lub uzgodnienia z badaczem,
     * `usun_identyfikator`: w przypadku wykrycia numeru PESEL lub danych osobowych,
     * `pozostaw_bez_zmiany`: gdy sprawdzona wartość wygląda podejrzanie, ale jest poprawna (uzasadnij to w kolumnie `problem`).
6. Dopisz w karcie kolumnę `wiersz_excel` z numerem wiersza z nieposortowanego oryginału. Ten sam `patient_id` może wystąpić w rejestrze dwa razy, a numer wiersza rozstrzyga, o który rekord chodzi. Aplikacja tę kolumnę pomija.
7. Cel: co najmniej 8 dobrze uzasadnionych wpisów z co najmniej 5 kategorii, w tym przynajmniej po jednym z decyzją `napraw_wg_slownika`, `zapytanie_do_osrodka` i `pozostaw_bez_zmiany`. 15 wpisów to cel dodatkowy.
8. Po 15 minutach prowadzący przedstawi ogólną listę kategorii błędów jako podpowiedź.
9. Na koniec zapisz kartę jako `karta_cw1.xlsx` i już jej nie zmieniaj. To jest wynik samego przeglądu ręcznego, potrzebny w Ćwiczeniu 4.

**Produkt do oddania:** plik `karta_cw1.xlsx`.

---

### Ćwiczenie 2: Eksploracja danych (EDA) i reguły walidacyjne (20 min, 0:30–0:50)
W tym ćwiczeniu wykorzystasz moduł analityczny aplikacji webowej.

1. Przejdź do zakładki **EDA** w aplikacji:
   - przejrzyj automatyczne zestawienie braków danych,
   - sprawdź unikalne wartości w kolumnach kategorycznych,
   - przeanalizuj histogramy i wykresy rozrzutu w poszukiwaniu wartości odstających.
2. Przejdź do zakładki **Reguły walidacyjne**:
   - uruchom predefiniowany zestaw reguł walidacyjnych,
   - zapoznaj się z wygenerowaną listą naruszeń jakościowych.
3. Dopisz 3 reguły: „Dodaj własną regułę” → „Wyrażenie pandas query”. Wyrażenie opisuje wiersze z błędem, np. `rt_technique == 'SBRT' and rt_fractions != 5`. Jedną regułę napisz samodzielnie, a dwie przez modyfikację przykładu. Przykładowe obszary:
   - zgodność grupy stopnia ISUP z sumą wzorców Gleasona,
   - SBRT w 5 frakcjach; to zasada protokołu tego rejestru, a nie ogólna reguła kliniczna (publikowano też SBRT w 4 frakcjach, np. 36 Gy/4 fr.: Kawakami i wsp., Radiat Oncol 2022;17:67),
   - nawrót biochemiczny Phoenix w uproszczeniu przyjętym w rejestrze: ostatnie PSA ≥ nadir + 2 ng/ml; pełna ocena wymaga historii PSA i leczenia,
   - zgodność statusu ADT z liczbą miesięcy terapii hormonalnej (brak ADT wymusza 0 miesięcy).
4. Dla każdej reguły wskaż jeden wiersz, który reguła powinna zgłosić, i jeden poprawny wiersz, którego nie powinna. Wartości tekstowe w kolumnach liczbowych (np. `<0,01`, `ok. 0,2`) reguła z wyrażeniem pomija; wyłapują je gotowe reguły typu i formatu.
5. Porównaj raport naruszeń z reguł z kartą `karta_cw1.xlsx`.
6. Zapisz kopię karty jako `karta_cw2.xlsx` i dopisz do niej problemy przeoczone w Ćwiczeniu 1. W nowej kolumnie `zrodlo` oznacz wpisy: `ręcznie` albo `reguła`.

**Produkt do oddania:** treść 3 reguł z wierszem, który każda zgłasza, i wierszem, którego nie zgłasza, oraz plik `karta_cw2.xlsx`.

---

### Przerwa (10 min, 0:50–1:00)

---

### Ćwiczenie 3: Ekstrakcja danych z dokumentacji medycznej przez model AI (30 min, 1:00–1:30)
W tym ćwiczeniu zbadasz, jak lokalny model językowy Ornith radzi sobie z przenoszeniem informacji z nieustrukturyzowanego tekstu klinicznego do tabeli rejestru.

1. Przejdź do zakładki **AI: ekstrakcja z dokumentów**.
2. Wybierz w polu „Dokumenty” teksty przydzielone Twojej grupie. Przydział zależy od numeru grupy n:
   - grupa n (od 1 do 15) wybiera dokumenty DOK-n, DOK-(n+15), DOK-(n+30) i DOK-(n+45), np. grupa 2: DOK-02, DOK-17, DOK-32, DOK-47 (tabela przydziału jest też na slajdzie).
3. Na razie wybierz tylko trzy pierwsze dokumenty z przydziału (np. grupa 2: DOK-02, DOK-17, DOK-32). Czwarty dokument zostaw do sprawdzenia poprawki i nie oglądaj go wcześniej.
4. Uruchom ekstrakcję domyślnym poleceniem (promptem) i obejrzyj porównanie z kluczem referencyjnym.
5. Zidentyfikuj i nazwij typowe błędy popełnione przez model:
   - pominięcie informacji obecnej w tekście,
   - halucynacja (zmyślenie wartości nieobecnej w dokumencie),
   - błąd przeliczenia jednostek (np. brak przeliczenia hemoglobiny z mmol/l na g/dl lub kreatyniny z µmol/l na mg/dl),
   - błędna interpretacja formatu daty (zamiana dnia z miesiącem w zapisie DD/MM/RRRR),
   - niepoprawne kodowanie negacji (np. wpisanie null zamiast 0 przy „nie stwierdzono cukrzycy” lub 0 zamiast null przy braku wzmianki).
6. Zasady klucza: model ma odtworzyć tylko informację zapisaną w dokumencie. Gdy dokument nie podaje wartości, poprawną odpowiedzią jest `null`; na przykład `adt_months` = 0 tylko wtedy, gdy dokument podaje „0 mies.”. Wynik poniżej granicy oznaczalności (`<0,01`) zapisujemy w polu liczbowym jako `null`; to zasada kodowania tego ćwiczenia, a nie brak pomiaru. Pole wyliczane `bcr_phoenix` klucz liczy regułą ze słownika, więc bez obu wartości punktowych PSA też jest `null`.
7. Zapisz jedną hipotezę, np. „model myli brak wzmianki z negacją”, i dopisz do polecenia zasadę, która ma ją naprawić.
8. Uruchom poprawione polecenie na tych samych trzech dokumentach i zapisz dokładność przed poprawką i po niej.
9. Sprawdzenie na nowym dokumencie: dodaj czwarty dokument, ustaw go w polu „Podgląd dokumentu” i odznacz „Wszystkie wybrane dokumenty”. Uruchom ekstrakcję poprawionym poleceniem, potem kliknij „Przywróć domyślne polecenie” i uruchom ją jeszcze raz. Porównaj dokładność obu wersji na czwartym dokumencie i już nie zmieniaj polecenia. Brak poprawy albo pogorszenie to też prawidłowy wynik.
10. Sprawdź jedno wybrane pole, np. `bcr_phoenix`: w ilu z czterech dokumentów model wpisał je poprawnie? Wysoka średnia zgodność nie gwarantuje poprawności pola, które jest punktem końcowym badania.

**Produkt do oddania:** hipoteza, dokładność na trzech dokumentach roboczych przed poprawką i po niej, dokładność obu wersji polecenia na czwartym dokumencie oraz wynik dla jednego wybranego pola.

---

### Ćwiczenie 4: AI jako drugi monitor jakości danych klinicznych (20 min, 1:30–1:50)
W tym ćwiczeniu ocenisz zdolność modelu AI do wykrywania niespójności w ustrukturyzowanej tabeli danych.

1. Przejdź do zakładki **AI: wiarygodność kliniczna**.
2. Uruchom audyt AI dla wierszy rejestru przypisanych do Twojej grupy:
   - grupa n analizuje wiersze od 20·(n−1)+1 do 20·n (wpisz je w polach „Pierwszy rekord” i „Ostatni rekord”); grupy 6 i 12 analizują wiersze 101–121,
   - grupy 7–15 analizują te same zakresy co grupy o numerze mniejszym o 6 lub 12 (np. grupa 8 jak grupa 2: wiersze 21–40).
3. Sprawdź każde podejrzenie AI w słowniku i w rejestrze.
4. Przejdź do zakładki **Porównanie z kluczem**, wgraj plik `karta_cw1.xlsx` (sam przegląd ręczny) i kliknij „Wczytaj znaleziska grupy”, a potem „Pokaż klucz”.
5. Aplikacja porówna klucz, reguły, AI i Twoją kartę na tych samych wierszach, które oceniało AI. Wpisy z decyzją `pozostaw_bez_zmiany` nie są liczone jako zgłoszenia błędów; aplikacja pokaże osobno, czy słusznie je pozostawiono.
6. Odczytaj dla każdej metody liczbę wykrytych błędów, fałszywych alarmów i precyzję, czyli odsetek trafnych zgłoszeń. Policz, ile zgłoszeń AI trzeba było sprawdzić i ile z nich okazało się błędami.
7. Zwróć uwagę na rzadkie, ale poprawne wartości kliniczne (pułapki): czy AI albo Twoja grupa zgłosiły je jako błędy?
8. Opcjonalnie wgraj `karta_cw2.xlsx` i zobacz, ile znalezisk dodały reguły. Kontrola duplikatów wymaga całego rejestru: ustaw zakres porównania 1–121.

**Produkt do oddania:** tabela porównawcza metod na wspólnym zakresie wierszy z liczbą fałszywych alarmów i precyzją.

---

### Podsumowanie (10 min, 1:50–2:00)
- Prowadzący omawia trzy reprezentatywne przypadki z pracy grup i listę kontrolną weryfikacji bazy przed przekazaniem do biostatystyka.
- Zadanie indywidualne (5 min): każdy uczestnik sam rozwiązuje dwa nowe przypadki ze slajdu i zapisuje, na czym polega problem, co może zrobić od razu, co wymaga sprawdzenia w źródle i jaką decyzję wpisze do karty. W grupach warto zmieniać osobę przy komputerze między ćwiczeniami.

---

## Co należy oddać po zajęciach
Każdy zespół zapisuje u siebie i pokazuje prowadzącemu podczas podsumowania:
1. Plik `karta_cw1.xlsx` z Ćwiczenia 1 oraz `karta_cw2.xlsx` uzupełniony po Ćwiczeniu 2.
2. Trzy reguły walidacyjne z Ćwiczenia 2 wraz z wierszami, które każda zgłasza i których nie zgłasza.
3. Wyniki Ćwiczenia 3: hipotezę, dokładność przed poprawką i po niej oraz wynik na czwartym dokumencie.
4. Tabelę porównania metod z Ćwiczenia 4 z precyzją i interpretacją fałszywych alarmów.

Każdy uczestnik oddaje też kartkę z zadaniem indywidualnym.
