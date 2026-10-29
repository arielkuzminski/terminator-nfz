"""Kreator `terminator-nfz setup`: wybór placówki i lekarzy, zapis config.toml i .env, test Telegrama."""

import os
import time
from pathlib import Path

import requests

from . import config
from .clinic import ClinicError
from .client import fetch_clinic, fetch_tile, make_session
from .config import MIN_INTERVAL_S, ConfigError, normalize_clinic_url
from .notify import bot_name, find_chats, telegram_sender
from .parser import FULL, NOT_PUBLISHED, parse_tile

VISIT_CHOICES = {"1": ["nfz"], "2": ["prywatna"], "3": ["nfz", "prywatna"]}


LEGEND = (
    "  „od …” = najbliższy wolny termin, „zajęte” = wszystkie terminy online zajęte (warto pilnować),\n"
    "  „—” = lekarz nie wystawia takich terminów online (zapis tylko telefonicznie)."
)


def status_summary(tile_html):
    """Np. „NFZ: zajęte | prywatnie: od 03.11 17:00”."""
    parts = []
    for kind, label in (("nfz", "NFZ"), ("prv", "prywatnie")):
        status = parse_tile(tile_html, kinds=(kind,))
        if status.slots:
            text = f"od {status.slots[0].when:%d.%m %H:%M}"
        else:
            text = {FULL: "zajęte", NOT_PUBLISHED: "—"}.get(status.state, "?")
        if kind == "nfz" or text != "—":
            parts.append(f"{label}: {text}")
    return " | ".join(parts)


def listing_order(doctors):
    return sorted(doctors, key=lambda d: (d.unit, d.specialty_id, d.name))


def parse_numbers(text, count):
    """„1 3”, „1,3”, „2-4” -> lista numerów z zakresu 1..count (ValueError przy błędzie)."""
    numbers = []
    for part in text.replace(",", " ").split():
        lo, _, hi = part.partition("-")
        lo, hi = int(lo), int(hi or lo)
        if not 1 <= lo <= hi <= count:
            raise ValueError(part)
        numbers.extend(n for n in range(lo, hi + 1) if n not in numbers)
    if not numbers:
        raise ValueError(text)
    return numbers


def read_env(path):
    values = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def update_env(path, values):
    """Ustawia podane klucze w pliku .env, zostawiając pozostałe linie bez zmian."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(values)
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and key in pending:
            lines[i] = f"{key}={pending.pop(key)}"
    lines += [f"{k}={v}" for k, v in pending.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def _yes(answer, default):
    answer = answer.strip().lower()
    return default if not answer else answer in ("t", "tak", "y", "yes")


def _choose_clinic(ask, say, session):
    while True:
        url = ask("Adres strony przychodni na lekarzebezkolejki.pl: ").strip()
        try:
            clinic = fetch_clinic(session, normalize_clinic_url(url))
        except (ConfigError, ClinicError) as exc:
            say(f"  ✗ {exc}")
            continue
        except requests.RequestException as exc:
            say(f"  ✗ Nie udało się otworzyć strony: {exc}")
            continue
        say(f"  ✓ {clinic.name}: {len(clinic.doctors)} lekarzy z rejestracją online")
        return clinic


def _show_doctors(say, session, doctors):
    say(f"\nSprawdzam aktualne terminy ({len(doctors)} lekarzy)…")
    unit = None
    for number, doctor in enumerate(doctors, 1):
        time.sleep(config.DELAY_BETWEEN_DOCTORS_S)
        try:
            state = status_summary(fetch_tile(session, doctor))
        except requests.RequestException:
            state = "?"
        if (doctor.unit, doctor.specialty_id) != unit:
            unit = (doctor.unit, doctor.specialty_id)
            say(f"\n  {doctor.unit or 'Bez nazwy poradni'}")
        say(f"  {number:>3}. {doctor.name:32} {doctor.description:38} [{state}]")
    say("\n" + LEGEND)


def _write_config(path, clinic, chosen, visit_types, interval):
    ids = []
    for doctor in chosen:
        if doctor.id not in ids:
            ids.append(doctor.id)
    names = {d.id: d.name for d in chosen}
    doctor_lines = "".join(f"    {i},  # {names[i]}\n" for i in ids)
    types = ", ".join(f'"{v}"' for v in visit_types)
    Path(path).write_text(
        "# Wygenerowane przez `terminator-nfz setup`. Opis pól: config.example.toml\n\n"
        f"# {clinic.name}\n"
        f'clinic_url = "{clinic.url}"\n\n'
        f"doctors = [\n{doctor_lines}]\n\n"
        "specialties = []\n"
        f"visit_types = [{types}]\n"
        f"interval_seconds = {interval}\n",
        encoding="utf-8",
    )


def _setup_config(ask, say, config_path):
    if Path(config_path).exists() and not _yes(ask(f"{config_path} już istnieje. Nadpisać? [t/N]: "), False):
        say(f"Zostawiam obecny {config_path}.")
        return

    session = make_session()
    clinic = _choose_clinic(ask, say, session)
    doctors = listing_order(clinic.doctors)
    _show_doctors(say, session, doctors)

    while True:
        try:
            numbers = parse_numbers(ask("\nNumery lekarzy do pilnowania (np. 1 3 albo 2-4): "), len(doctors))
            break
        except ValueError:
            say(f"  ✗ Podaj numery z listy (1–{len(doctors)}).")
    chosen = [doctors[n - 1] for n in numbers]
    say("  ✓ " + ", ".join(d.name for d in chosen))

    visit_types = None
    while visit_types is None:
        answer = ask("\nJakie wizyty zgłaszać? 1 = NFZ, 2 = prywatne, 3 = oba [1]: ").strip() or "1"
        visit_types = VISIT_CHOICES.get(answer)
        if visit_types is None:
            say("  ✗ Wpisz 1, 2 albo 3.")

    while True:
        answer = ask("Co ile sekund sprawdzać? [90]: ").strip() or "90"
        if answer.isdigit() and int(answer) >= MIN_INTERVAL_S:
            interval = int(answer)
            break
        say(f"  ✗ Podaj liczbę sekund, co najmniej {MIN_INTERVAL_S}.")

    _write_config(config_path, clinic, chosen, visit_types, interval)
    say(f"\n✓ Zapisano {config_path}")


def _setup_telegram(ask, ask_secret, say, env_path):
    env = read_env(env_path)
    if env.get("TELEGRAM_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
        if not _yes(ask("\nTelegram jest już skonfigurowany w .env. Zmienić? [t/N]: "), False):
            return
    elif not _yes(ask("\nSkonfigurować teraz powiadomienia Telegram? [T/n]: "), True):
        say("Pominięto. Możesz wrócić do tego później: terminator-nfz setup")
        return

    say("\nJeśli nie masz bota: napisz na Telegramie do @BotFather, wyślij /newbot i skopiuj token.")
    while True:
        token = ask_secret("Token bota: ").strip()
        name = bot_name(token) if token else None
        if name:
            break
        say("  ✗ Telegram nie rozpoznaje tego tokenu. Skopiuj go jeszcze raz od @BotFather.")
    say(f"  ✓ Bot @{name}")

    while True:
        ask(f"\nNapisz teraz cokolwiek do @{name} na Telegramie i naciśnij Enter… ")
        chats = find_chats(token)
        if chats:
            break
        say("  ✗ Nie widzę jeszcze żadnej wiadomości do bota. Spróbuj ponownie.")
    chat_id, label = chats[0]
    if len(chats) > 1:
        for number, (cid, lbl) in enumerate(chats, 1):
            say(f"  {number}. {lbl}")
        while True:
            try:
                chat_id, label = chats[parse_numbers(ask("Do której rozmowy wysyłać? "), len(chats))[0] - 1]
                break
            except ValueError:
                say("  ✗ Podaj numer z listy.")

    update_env(env_path, {"TELEGRAM_TOKEN": token, "TELEGRAM_CHAT_ID": str(chat_id)})
    telegram_sender(token, chat_id)("✅ Terminator NFZ skonfigurowany. Tutaj przyjdą powiadomienia o wolnych terminach.")
    say(f"  ✓ Zapisano {env_path} i wysłano wiadomość testową do: {label}")


def run_setup(ask=input, ask_secret=None, say=print, config_path="config.toml", env_path=".env"):
    if ask_secret is None:
        import getpass

        ask_secret = getpass.getpass
    say("Terminator NFZ – konfiguracja\n")
    _setup_config(ask, say, config_path)
    _setup_telegram(ask, ask_secret, say, env_path)
    say("\nGotowe! Sprawdzenie bez wysyłania:  terminator-nfz run --once --dry-run")
    say("Start pilnowania terminów:          terminator-nfz run")
