# Instrukcja ćwiczeń: Higiena i jakość danych klinicznych w onkologii

## Informacje organizacyjne
- Prowadzący: dr n. med. Konrad Stawiski
- Odbiorcy: lekarze, uczestnicy studiów podyplomowych Uniwersytetu Medycznego w Łodzi
- Czas trwania: 120 minut
- Adres aplikacji: https://cwiczenia.radioonkolog.pl
- Login: `student`
- Hasło: przekaże prowadzący na początku zajęć

## Cel ćwiczeń
Celem zajęć jest opanowanie praktycznych metod wykrywania i korygowania błędów w medycznych bazach danych. Podczas ćwiczeń wykorzystasz tradycyjny arkusz kalkulacyjny, deterministyczne reguły walidacyjne oraz lokalny model językowy sztucznej inteligencji. Nauczysz się odróżniać błędy techniczne od rzadkich sytuacji klinicznych oraz poznasz standardy przygotowania danych do analizy statystycznej.

## Zasady bezpieczeństwa danych
1. Wszystkie dane używane na zajęciach są danymi syntetycznymi. Rejestr PROSTATA-RT oraz teksty dokumentacji medycznej zostały wygenerowane sztucznie.
2. Imiona, nazwiska oraz numery identyfikacyjne są fikcyjne. Numery o strukturze PESEL mają celowo błędną cyfrę kontrolną.
3. W codziennej pracy klinicznej nigdy nie wklejaj prawdziwych danych pacjentów do publicznych narzędzi internetowych ani czatów komercyjnych.
4. Prawdziwe dane pacjentów można przetwarzać modelem językowym tylko lokalnie, na sprzęcie zatwierdzonym przez instytucję i za jej zgodą.

## Organizacja pracy w zespołach
- Ćwiczenia wykonujemy w grupach 2–3-osobowych.
- Każda grupa po zalogowaniu na platformie wpisuje swoją nazwę w formacie: `Grupa X` (gdzie X to numer przypisany przez prowadzącego).
- Numer grupy wyznacza przydział dokumentów do ekstrakcji oraz zakres wierszy rejestru do audytu.

---

## Krótka ściąga funkcji arkusza kalkulacyjnego

Do sprawnej pracy z brudnym rejestrem w programach Microsoft Excel oraz LibreOffice Calc przydadzą się podstawowe mechanizmy filtrowania, sortowania i formuł logicznych.

| Zadanie | Excel (polski / angielski) | LibreOffice Calc |
|---|---|---|
| Filtry | Dane → Filtruj / Data → Filter | Dane → Autofiltr |
| Sortowanie | Dane → Sortuj / Data → Sort | Dane → Sortuj |
| Wyróżnienie komórek | Narzędzia główne → Formatowanie warunkowe / Home → Conditional Formatting | Format → Warunkowe |
| Czy to liczba? | `=CZY.LICZBA(A2)` / `=ISNUMBER(A2)` | `=CZY.LICZBA(A2)` |
| Usunięcie spacji | `=USUŃ.ZBĘDNE.ODSTĘPY(A2)` / `=TRIM(A2)` | `=USUŃ.ZBĘDNE.ODSTĘPY(A2)` |
| Duplikaty ID | `=LICZ.JEŻELI($A$2:$A$122;A2)` / `=COUNTIF($A$2:$A$122,A2)` | `=LICZ.JEŻELI($A$2:$A$122;A2)` |

Wynik `CZY.LICZBA` = FAŁSZ w kolumnie liczbowej oznacza liczbę zapisaną jako tekst (np. `12,4 ng/ml`). Wynik `LICZ.JEŻELI` większy niż 1 oznacza powtórzony identyfikator.

### Przydatne triki:
- Separator dziesiętny: upewnij się, czy Twój system używa przecinka, czy kropki. Niezgodność separatora powoduje traktowanie liczb jako tekst.
- Apostrof przed tekstem: wpisanie znaku `'` na początku komórki wymusza format tekstowy i blokuje autokonwersję zapisu (np. zapobiega zamianie `3-4` na datę).

---

## Przebieg ćwiczeń krok po kroku

### Start (0:00–0:05): Przygotowanie stanowiska
1. Wejdź na stronę https://cwiczenia.radioonkolog.pl.
2. Zaloguj się loginem `student` i hasłem podanym przez prowadzącego.
3. Wpisz nazwę swojej grupy w aplikacji.
4. Przejdź do zakładki Start i pobierz pliki robocze: `rejestr_brudny.xlsx`, `slownik_danych.xlsx` (lub `.csv`) oraz `karta_znalezisk.xlsx`.
5. Zapisz kopię roboczą pliku `rejestr_brudny.xlsx` na swoim dysku.

---

### Ćwiczenie 1: Detektyw bez AI (25 min, 0:05–0:30)
Pracujesz wyłącznie na pliku `rejestr_brudny.xlsx` bez użycia algorytmów sztucznej inteligencji. Masz przed sobą rejestr 120 chorych poddanych radioterapii z powodu raka gruczołu krokowego.

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
4. Każdy zidentyfikowany błąd wpisz do pliku `karta_znalezisk.xlsx`.
5. W karcie znalezisk wypełnij kolumny:
   - `patient_id`: identyfikator pacjenta z danego wiersza,
   - `zmienna`: nazwa kolumny, w której występuje problem,
   - `problem`: krótki opis zaobserwowanej nieprawidłowości,
   - `decyzja`: wybierz jedną z trzech dopuszczalnych opcji:
     * `napraw_wg_slownika`: gdy błąd jest jednoznaczny i słownik precyzuje poprawny zapis,
     * `zapytanie_do_osrodka`: gdy błąd wymaga weryfikacji w dokumentacji źródłowej lub uzgodnienia z badaczem,
     * `usun_identyfikator`: w przypadku wykrycia numeru PESEL lub danych osobowych.
6. Cel minimalny grupy: odnalezienie co najmniej 15 nieprawidłowości.
7. Po 15 minutach prowadzący przedstawi ogólną listę kategorii błędów jako podpowiedź.

**Produkt do oddania:** wypełniony plik `karta_znalezisk.xlsx` (minimum 15 wierszy).

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
3. Dopisz 3 własne reguły: „Dodaj własną regułę” → „Wyrażenie pandas query”. Wyrażenie opisuje wiersze z błędem, np. `rt_technique == 'SBRT' and rt_fractions != 5`. Przykładowe obszary:
   - zgodność grupy stopnia ISUP z sumą wzorców Gleasona,
   - dopuszczalność techniki SBRT wyłącznie przy 5 frakcjach,
   - kryterium nawrotu biochemicznego Phoenix (ostatnie PSA >= nadir + 2 ng/ml),
   - zgodność statusu ADT z liczbą miesięcy terapii hormonalnej (brak ADT wymusza 0 miesięcy).
4. Porównaj raport naruszeń z reguł z własną kartą znalezisk z Ćwiczenia 1.
5. Uzupełnij w pliku `karta_znalezisk.xlsx` te problemy, które zostały przeoczone podczas manualnego przeglądu.

**Produkt do oddania:** lista naruszeń wygenerowana przez reguły oraz treść 3 dopisanych reguł.

---

### Przerwa (10 min, 0:50–1:00)

---

### Ćwiczenie 3: Ekstrakcja danych z dokumentacji medycznej przez model AI (30 min, 1:00–1:30)
W tym ćwiczeniu zbadasz, jak lokalny model językowy Ornith radzi sobie z przenoszeniem informacji z nieustrukturyzowanego tekstu klinicznego do tabeli rejestru.

1. Przejdź do zakładki **AI: ekstrakcja z dokumentów**.
2. Wybierz w polu „Dokumenty” teksty przydzielone Twojej grupie. Przydział zależy od numeru grupy n:
   - grupa n (od 1 do 15) wybiera dokumenty DOK-n, DOK-(n+15), DOK-(n+30) i DOK-(n+45), np. grupa 2: DOK-02, DOK-17, DOK-32, DOK-47 (tabela przydziału jest też na slajdzie).
3. Uruchom ekstrakcję danych za pomocą domyślnego polecenia (promptu) systemowego.
4. Obejrzyj automatyczne porównanie wyników ekstrakcji z kluczem referencyjnym.
5. Zidentyfikuj i nazwij typowe błędy popełnione przez model:
   - pominięcie informacji obecnej w tekście,
   - halucynacja (zmyślenie wartości nieobecnej w dokumencie),
   - błąd przeliczenia jednostek (np. brak przeliczenia hemoglobiny z mmol/l na g/dl lub kreatyniny z µmol/l na mg/dl),
   - błędna interpretacja formatu daty (zamiana dnia z miesiącem w zapisie DD/MM/RRRR),
   - niepoprawne kodowanie negacji (np. wpisanie null zamiast 0 przy braku cukrzycy lub wpisanie 0 zamiast null przy braku wzmianki).
6. Zmodyfikuj polecenie systemowe (prompt):
   - dodaj ścisłe instrukcje dotyczące przeliczania jednostek,
   - sprecyzuj regułę: brak informacji w tekście oznacza wartość `null`,
   - zdefiniuj format daty.
7. Uruchom ekstrakcję ponownie z poprawionym poleceniem.
8. Odnotuj wskaźnik dokładności modelu przed i po modyfikacji promptu.

**Produkt do oddania:** raport dokładności ekstrakcji przed i po modyfikacji polecenia wraz z listą zaobserwowanych typów błędów.

---

### Ćwiczenie 4: AI jako drugi monitor jakości danych klinicznych (20 min, 1:30–1:50)
W tym ćwiczeniu ocenisz zdolność modelu AI do wykrywania niespójności w ustrukturyzowanej tabeli danych.

1. Przejdź do zakładki **AI: wiarygodność kliniczna**.
2. Uruchom audyt AI dla 20 wierszy rejestru przypisanych do Twojej grupy:
   - grupa n analizuje wiersze od 20·(n−1)+1 do 20·n (wpisz je w polach „Pierwszy rekord” i „Ostatni rekord”),
   - grupy 7–15 analizują te same zakresy co grupy o numerze mniejszym o 6 lub 12 (np. grupa 8 jak grupa 2: wiersze 21–40).
3. Przejdź do zakładki **Porównanie z kluczem**, wgraj swój plik `karta_znalezisk.xlsx` i kliknij „Wczytaj znaleziska grupy”.
4. Aplikacja zestawi ze sobą wyniki trzech metod nadzoru:
   - liczbę błędów znalezionych manualnie przez człowieka,
   - liczbę błędów wykrytych przez reguły deterministyczne,
   - liczbę błędów zaraportowanych przez model AI.
5. Zwróć szczególną uwagę na liczbę fałszywych alarmów podniesionych przez model AI, zwłaszcza na przypadki zakwalifikowania rzadkich, lecz poprawnych wartości klinicznych (pułapek) jako błędy.

**Produkt do oddania:** tabela porównawcza skuteczności metod („kto co złapał”) wraz z podsumowaniem fałszywych alarmów.

---

### Podsumowanie (10 min, 1:50–2:00)
- Przedstawiciel każdej grupy podaje jeden najważniejszy wniosek z wykonanych ćwiczeń.
- Prowadzący omawia listę kontrolną weryfikacji bazy przed przekazaniem do biostatyka.

---

## Co należy oddać po zajęciach
Każdy zespół zapisuje u siebie i pokazuje prowadzącemu podczas podsumowania:
1. Uzupełniony plik `karta_znalezisk.xlsx` z Ćwiczenia 1 (uzupełniony po Ćwiczeniu 2).
2. Tekst 3 własnych reguł walidacyjnych opracowanych w Ćwiczeniu 2.
3. Wskaźniki dokładności ekstrakcji z Ćwiczenia 3 (przed i po poprawie promptu) z krótkim opisem błędów modelu.
4. Zbiorczą tabelę porównania metod z Ćwiczenia 4 z interpretacją fałszywych alarmów.
