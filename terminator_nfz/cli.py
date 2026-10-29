"""Polecenia: setup, doctors, run, test-notify, telegram-chats."""

import argparse
import os
import sys
import time
from pathlib import Path

from . import __version__, config
from .clinic import ClinicError
from .client import fetch_clinic, fetch_tile, make_session
from .config import Config, ConfigError, load_config, normalize_clinic_url
from .notify import find_chats, print_sender, telegram_sender
from .watch import watch
from .wizard import LEGEND, listing_order, run_setup, status_summary


def load_dotenv(path=".env"):
    """Wczytuje KEY=VALUE z pliku .env; nie nadpisuje zmiennych już ustawionych w środowisku."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def cmd_doctors(args):
    if args.url:
        cfg = Config(clinic_url=normalize_clinic_url(args.url))
    else:
        cfg = load_config(args.config)
    session = make_session()
    clinic = fetch_clinic(session, cfg.clinic_url)
    print(f"{clinic.name} – {clinic.url}\n")
    unit = None
    for doctor in listing_order(clinic.doctors):
        if (doctor.unit, doctor.specialty_id) != unit:
            unit = (doctor.unit, doctor.specialty_id)
            print(f"\n{doctor.unit or 'Bez nazwy poradni'}  (specialties: {doctor.specialty_id})")
        watched = "✓" if doctor.id in cfg.doctors else " "
        line = f" {watched} {doctor.id:>8}  {doctor.name:32} {doctor.description}"
        if args.status:
            time.sleep(config.DELAY_BETWEEN_DOCTORS_S)
            line += f"  [{status_summary(fetch_tile(session, doctor))}]"
        print(line)
    if args.status:
        print("\n" + LEGEND)
    print("\nWpisz wybrane numery do config.toml, np. doctors = [1234567, 2345678]")


def cmd_setup(args):
    run_setup(config_path=args.config, env_path=args.env)


def cmd_run(args):
    cfg = load_config(args.config)
    if args.interval is not None:
        if args.interval < config.MIN_INTERVAL_S:
            raise ConfigError(f"--interval musi wynosić co najmniej {config.MIN_INTERVAL_S}")
        cfg.interval_seconds = args.interval
    send = print_sender if args.dry_run else telegram_sender()
    return watch(cfg, args.state, send, minutes=args.minutes, once=args.once, verbose=args.once or args.dry_run)


def cmd_test_notify(_args):
    telegram_sender()("✅ Test: Terminator NFZ działa i może wysyłać powiadomienia.")
    print("Wysłano wiadomość testową.")


def cmd_telegram_chats(args):
    token = args.token or os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise SystemExit("Podaj token: terminator-nfz telegram-chats <TOKEN> albo ustaw TELEGRAM_TOKEN w .env")
    chats = find_chats(token)
    if not chats:
        print("Brak rozmów. Napisz cokolwiek do swojego bota na Telegramie i uruchom polecenie ponownie.")
        return
    for chat_id, label in chats:
        print(f"TELEGRAM_CHAT_ID={chat_id}    # {label}")


def build_parser():
    p = argparse.ArgumentParser(prog="terminator-nfz", description="Powiadomienia o wolnych terminach z lekarzebezkolejki.pl")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("setup", help="kreator: wybór przychodni i lekarzy, konfiguracja Telegrama")
    s.add_argument("--config", default="config.toml")
    s.add_argument("--env", default=".env")
    s.set_defaults(func=cmd_setup)

    d = sub.add_parser("doctors", help="pokaż lekarzy placówki i ich numery (id)")
    d.add_argument("--config", default="config.toml")
    d.add_argument("--url", help="adres placówki (zamiast clinic_url z config.toml)")
    d.add_argument("--status", action="store_true", help="sprawdź też aktualne terminy każdego lekarza")
    d.set_defaults(func=cmd_doctors)

    r = sub.add_parser("run", help="sprawdzaj terminy i wysyłaj powiadomienia")
    r.add_argument("--config", default="config.toml")
    r.add_argument("--state", default="state.json", help="plik z zapamiętanymi terminami")
    r.add_argument("--once", action="store_true", help="jedna runda i koniec")
    r.add_argument("--minutes", type=float, help="zakończ po tylu minutach (domyślnie: bez końca)")
    r.add_argument("--interval", type=float, help="sekundy między rundami (nadpisuje config.toml)")
    r.add_argument("--dry-run", action="store_true", help="nie wysyłaj na Telegram, tylko wypisz")
    r.set_defaults(func=cmd_run)

    t = sub.add_parser("test-notify", help="wyślij wiadomość testową na Telegram")
    t.set_defaults(func=cmd_test_notify)

    c = sub.add_parser("telegram-chats", help="pokaż TELEGRAM_CHAT_ID rozmów z botem")
    c.add_argument("token", nargs="?")
    c.set_defaults(func=cmd_telegram_chats)
    return p


def main(argv=None):
    load_dotenv()
    args = build_parser().parse_args(argv)
    try:
        code = args.func(args)
    except (ConfigError, ClinicError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        code = 2
    except KeyboardInterrupt:
        code = 130
    sys.exit(code or 0)
