# Terminator NFZ

Wiadomość na Telegramie, gdy tylko u wybranego lekarza zwolni się termin. Działa z każdą przychodnią, która
zapisuje pacjentów przez [lekarzebezkolejki.pl](https://lekarzebezkolejki.pl).

```
🩺 Wolny termin – Przychodnia Przykładowa

Anna Kowalska – Wizyta NFZ
📅 pt. 30.10 08:30 (jutro)
👉 Zarezerwuj ten termin
Terminarz lekarza
```

Wiele przychodni wystawia terminy online tylko na dzień lub dwa do przodu, a wolne miejsca znikają w kilka minut.
Terminator sprawdza je co półtorej minuty i daje znać, zanim zrobi to ktoś inny. Zapisujesz się sam, jednym
kliknięciem w link z wiadomości.

## Spis treści

1. [Jak to działa](#jak-to-działa)
2. [Instalacja](#instalacja)
3. [Konfiguracja](#konfiguracja)
4. [Uruchamianie](#uruchamianie)
5. [Polecenia](#polecenia)
6. [Rozwiązywanie problemów](#rozwiązywanie-problemów)
7. [Ograniczenia i zasady](#ograniczenia-i-zasady)
8. [Licencja](#licencja)

## Jak to działa

1. Ze strony przychodni program odczytuje listę lekarzy wraz z parametrami ich terminarzy.
2. Co `interval_seconds` sekund pobiera dla każdego wybranego lekarza ten sam fragment strony, który widzisz w
   przeglądarce: najbliższy wolny termin NFZ lub prywatny. Logowanie nie jest potrzebne.
3. Każdy **nowy** termin wysyła na Telegram. Termin, o którym już powiadomił, nie przyjdzie drugi raz (pamięta je w
   `state.json`).
4. Gdy strona przestanie odpowiadać albo zmieni wygląd (np. przy blokadzie), po 3 nieudanych rundach z rzędu
   przyśle ostrzeżenie, a po powrocie do normy jedno „znowu działa”. Nie zamilknie więc po cichu.

## Instalacja

Wymagany jest Python 3.10 lub nowszy.

```bash
git clone https://github.com/arielkuzminski/terminator-nfz.git
cd terminator-nfz
python3 -m venv .venv
.venv/bin/pip install .
```

Dalej w instrukcji `terminator-nfz` oznacza `.venv/bin/terminator-nfz`. Możesz też aktywować środowisko
poleceniem `source .venv/bin/activate`.

## Konfiguracja

### Najprościej: kreator

```bash
terminator-nfz setup
```

Kreator po kolei:
1. pyta o adres przychodni,
2. pokazuje ponumerowaną listę lekarzy z aktualnymi terminami; wpisujesz np. `1 5`,
3. pyta, czy pilnować wizyt NFZ, prywatnych, czy obu, i co ile sekund sprawdzać,
4. łączy się z Twoim botem na Telegramie: sam znajduje chat id i wysyła wiadomość testową,
5. zapisuje `config.toml` i `.env`.

Potem przejdź od razu do [Uruchamiania](#uruchamianie). Poniżej to samo krok po kroku, ręcznie.

### 1. Znajdź swoją przychodnię

Wejdź na [lekarzebezkolejki.pl](https://lekarzebezkolejki.pl), wyszukaj przychodnię i otwórz jej stronę. Adres
wygląda np. tak: `https://lekarzebezkolejki.pl/placowka/NazwaPrzychodni.Miasto`. Skopiuj go.

> Na stronie przychodni muszą być widoczne terminy z przyciskami „Zarezerwuj” lub komunikaty w stylu „Zajęte są
> wszystkie udostępnione terminy…”. Jeśli są tam tylko dane kontaktowe, przychodnia nie prowadzi zapisów online i
> program nic nie znajdzie.

### 2. Wybierz lekarzy

```bash
terminator-nfz doctors --url https://lekarzebezkolejki.pl/placowka/NazwaPrzychodni.Miasto --status
```

```
PORADNIA (GABINET) LEKARZA POZ  (specialties: 3081)
    1234567  Anna Kowalska                    lekarz medycyny ogólnej  [NFZ: zajęte]
    2345678  Jan Nowak                        lekarz rodzinny  [NFZ: od 30.10 08:15]
       3456  Ewa Wiśniewska                   lekarz rodzinny, pediatra  [NFZ: —]

PORADNIA GINEKOLOGICZNO - POŁOŻNICZA  (specialties: 3227)
       4567  Piotr Zieliński                  ginekolog  [NFZ: zajęte | prywatnie: od 03.11 17:00]
    ...
```

Liczba przed nazwiskiem to **id** lekarza, a `specialties` to numer poradni. `--status` dopisuje stan terminarza:

| Status | Znaczenie |
|---|---|
| `od 30.10 08:15` | najbliższy wolny termin |
| `zajęte` | wszystkie terminy wystawione online są zajęte; warto pilnować |
| `—` | lekarz nie wystawia takich terminów online (zapis tylko telefonicznie); nie ma sensu go pilnować |

> Opis na stronie nie zawsze mówi wszystko. Na przykład „lekarz rodzinny” może przyjmować tylko dzieci. W razie
> wątpliwości zapytaj w rejestracji.

### 3. Uzupełnij `config.toml`

```bash
cp config.example.toml config.toml
```

```toml
clinic_url = "https://lekarzebezkolejki.pl/placowka/NazwaPrzychodni.Miasto"
doctors = [1234567, 2345678]   # id z `terminator-nfz doctors`; [] = wszyscy
specialties = []               # np. [3081] = tylko POZ; [] = wszystkie
visit_types = ["nfz"]          # "nfz", "prywatna" albo obie
interval_seconds = 90          # minimum 30
```

Filtry `doctors` i `specialties` działają razem. Na przykład `doctors = []` i `specialties = [3081]` oznacza
wszystkich lekarzy POZ w przychodni.

### 4. Podłącz Telegram

1. Na Telegramie napisz do [@BotFather](https://t.me/BotFather), wyślij `/newbot` i nadaj botowi nazwę. Dostaniesz
   **token**. Możesz też użyć bota, którego już masz.
2. Napisz cokolwiek do swojego bota. Telegram nie pozwala botowi pisać do kogoś, kto nie zaczął rozmowy.
3. Odczytaj chat id:
   ```bash
   terminator-nfz telegram-chats <TOKEN>
   ```
4. Utwórz w katalogu projektu plik `.env`. Nigdy nie trafia do gita.
   ```
   TELEGRAM_TOKEN=123456:ABC...
   TELEGRAM_CHAT_ID=123456789
   ```
5. Sprawdź, czy wiadomość dochodzi:
   ```bash
   terminator-nfz test-notify
   ```

### 5. Pierwsze sprawdzenie

```bash
terminator-nfz run --once --dry-run
```

Polecenie wykona jedną rundę i pokaże stan każdego lekarza. Nie wysyła nic na Telegram.

## Uruchamianie

### Na próbę, w terminalu

```bash
terminator-nfz run
```

Program działa, dopóki go nie zatrzymasz (Ctrl+C). Opcja `--minutes 120` kończy pracę po 2 godzinach.

### Na stałe: systemd (Linux, Raspberry Pi, serwer)

```bash
mkdir -p ~/.config/systemd/user
cp deploy/terminator-nfz.service ~/.config/systemd/user/
# jeśli repo nie leży w ~/terminator-nfz, popraw ścieżki w pliku usługi
systemctl --user daemon-reload
systemctl --user enable --now terminator-nfz
loginctl enable-linger "$USER"        # żeby działało też po wylogowaniu
journalctl --user -u terminator-nfz -f   # podgląd logów
```

Na WSL najpierw włącz systemd: w `/etc/wsl.conf` dodaj sekcję `[boot]` z linią `systemd=true`, a potem w Windows
uruchom `wsl --shutdown`. WSL działa tylko wtedy, gdy komputer jest włączony.

### Na stałe: cron

```cron
*/15 * * * * cd ~/terminator-nfz && flock -n /tmp/terminator-nfz.lock .venv/bin/terminator-nfz run --minutes 14 >> logs.txt 2>&1
```

### Na stałe: GitHub Actions (bez własnego komputera)

Repozytorium zawiera gotowy workflow `.github/workflows/watch.yml`. Startuje co 15 minut, sprawdza terminy co 90 s
przez 14 minut, a zapamiętane terminy trzyma w gałęzi `state`.

1. Zrób fork lub kopię repozytorium jako **publiczne** repo. W prywatnym darmowy limit 2000 minut miesięcznie
   skończy się po kilku dniach.
2. *Settings → Secrets and variables → Actions*:
   - **Secrets**: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`
   - **Variables**: `TERMINATOR_CONFIG` z całą zawartością Twojego `config.toml`. Twoja konfiguracja nie leży
     wtedy w kodzie, który widzi każdy.
3. *Actions* → włącz workflowy → `watch` → **Run workflow**, żeby sprawdzić, czy działa.

Bez zmiennej `TERMINATOR_CONFIG` workflow jest pomijany. Cron GitHuba bywa opóźniony o kilka do kilkunastu minut,
więc czasem w sprawdzaniu jest przerwa. Jeśli zależy Ci na każdej minucie, wybierz systemd.

## Polecenia

| Polecenie | Co robi |
|---|---|
| `terminator-nfz setup` | kreator: przychodnia, lekarze, Telegram; zapisuje `config.toml` i `.env` |
| `terminator-nfz doctors [--url URL] [--status]` | lista lekarzy przychodni z numerami id; ✓ przy pilnowanych |
| `terminator-nfz run` | sprawdza terminy w pętli i wysyła powiadomienia |
| `terminator-nfz run --once --dry-run` | jedna runda, bez wysyłania; dobre do testu konfiguracji |
| `terminator-nfz test-notify` | wysyła wiadomość testową na Telegram |
| `terminator-nfz telegram-chats [TOKEN]` | pokazuje `TELEGRAM_CHAT_ID` rozmów z botem |

Opcje `run`: `--config PLIK` (domyślnie `config.toml`), `--state PLIK` (domyślnie `state.json`),
`--minutes N`, `--interval S`, `--once`, `--dry-run`.

Żeby pilnować kilku przychodni, uruchom osobne procesy z różnymi plikami, np.
`--config przychodnia2.toml --state przychodnia2.json`.

## Rozwiązywanie problemów

| Objaw | Co zrobić |
|---|---|
| `Brak pliku config.toml` | uruchom `terminator-nfz setup` (albo `cp config.example.toml config.toml` i uzupełnij) |
| `nie ma lekarzy z rejestracją online` | przychodnia nie prowadzi zapisów przez lekarzebezkolejki.pl albo adres jest zły |
| `Żaden lekarz … nie pasuje do konfiguracji` | sprawdź `doctors` i `specialties` z wynikiem `terminator-nfz doctors` |
| `Brak TELEGRAM_TOKEN / TELEGRAM_CHAT_ID` | uzupełnij `.env` w katalogu, z którego uruchamiasz program |
| `telegram-chats` nic nie pokazuje | najpierw napisz cokolwiek do bota |
| Na Telegram przyszło ostrzeżenie „nie może sprawdzić terminów” | strona nie odpowiada albo zmieniła wygląd; jeśli to blokada, zwiększ `interval_seconds` (np. do 300) |
| Lekarz ciągle `NOT_PUBLISHED` | ten lekarz nie wystawia terminów online; zostaje telefon |

## Ograniczenia i zasady

- **To nieoficjalne narzędzie.** Nie jest powiązane z LekarzeBezKolejki.pl, Kamsoft S.A., NFZ ani żadną
  przychodnią. Korzysta z tych samych publicznych stron, które widzi każdy odwiedzający. Gdy serwis zmieni
  wygląd, program może przestać działać; wtedy wyśle ostrzeżenie.
- **Nie rezerwuje za Ciebie.** Tylko powiadamia. Zapisujesz się sam, a w razie wątpliwości dzwonisz do rejestracji.
- **Bądź łaskawy dla serwera.** Pilnuj tylko lekarzy, których potrzebujesz, i nie schodź poniżej domyślnych 90 s.
  Program wymusza minimum 30 s i robi przerwę między zapytaniami.
- Na stronie przychodni widać tylko **najbliższy** wolny termin każdego lekarza. Gdy ktoś go zajmie i pojawi się
  następny, dostaniesz nowe powiadomienie.
- Daty i godziny są w czasie polskim (Europe/Warsaw).

## Rozwój

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

Testy działają na zapisanych prawdziwych odpowiedziach serwisu (`tests/fixtures/`) i nie łączą się z internetem.

## Licencja

[MIT](LICENSE). Program jest darmowy: możesz go używać, kopiować, zmieniać i rozpowszechniać, także w zmienionej
wersji. Program jest udostępniony „tak jak jest”, bez żadnej gwarancji.
