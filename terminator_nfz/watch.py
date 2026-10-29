"""Rundy sprawdzania terminów i pętla, która je powtarza."""

import html
import time
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .clinic import ClinicError, select_doctors
from .client import fetch_clinic, fetch_tile, make_session
from .parser import UNKNOWN, parse_tile
from .state import State

WEEKDAYS = ["pon.", "wt.", "śr.", "czw.", "pt.", "sob.", "niedz."]


def now_local():
    return datetime.now(ZoneInfo(config.TIMEZONE)).replace(tzinfo=None)


def slot_key(doctor, slot):
    return f"{doctor.key}|{slot.kind}|{slot.when.isoformat(timespec='minutes')}"


def format_slots(found, now, title):
    lines = [f"🩺 <b>Wolny termin – {html.escape(title)}</b>", ""]
    for doctor, slot in found:
        day = {now.date(): "dziś", (now + timedelta(days=1)).date(): "jutro"}.get(slot.when.date())
        when = f"{WEEKDAYS[slot.when.weekday()]} {slot.when:%d.%m %H:%M}" + (f" ({day})" if day else "")
        lines.append(f"<b>{html.escape(doctor.name)}</b> – {html.escape(slot.label)}")
        lines.append(f"📅 {when}")
        if slot.booking_path:
            lines.append(f'👉 <a href="{html.escape(config.BASE_URL + slot.booking_path)}">Zarezerwuj ten termin</a>')
        lines.append(f'<a href="{html.escape(doctor.url)}">Terminarz lekarza</a>')
        lines.append("")
    return "\n".join(lines).strip()


def update_health(state, problems, send):
    """Ostrzeżenie po FAIL_ALERT_ROUNDS nieudanych rundach z rzędu i jedna wiadomość po powrocie do normy."""
    if problems:
        state.fail_streak += 1
        if state.fail_streak >= config.FAIL_ALERT_ROUNDS and not state.failure_alerted:
            send("⚠️ <b>Terminator NFZ nie może sprawdzić terminów</b>\n\n" + html.escape("\n".join(problems)))
            state.failure_alerted = True
        return True
    if state.fail_streak:
        if state.failure_alerted:
            send("✅ Terminator NFZ znowu działa.")
        state.fail_streak = 0
        state.failure_alerted = False
        return True
    return False


def run_round(doctors, fetch, state, send, now, kinds, title, problems=(), log=lambda _msg: None):
    """Jedna runda sprawdzania. Zwraca True, gdy stan się zmienił i trzeba go zapisać."""
    changed = False
    problems = list(problems)
    found, states = [], Counter()

    for doctor in doctors:
        try:
            status = parse_tile(fetch(doctor), kinds=kinds)
        except Exception as exc:  # błąd sieci/HTTP liczymy jako nieudane sprawdzenie
            problems.append(f"{doctor.name}: {exc}")
            states["ERROR"] += 1
            continue
        states[status.state] += 1
        log(f"  {doctor.name}: {status.state} {status.note}")
        if status.state == UNKNOWN:
            problems.append(f"{doctor.name}: nierozpoznana odpowiedź ({status.note[:80]})")
            continue
        for slot in status.slots:
            if slot.when >= now and slot_key(doctor, slot) not in state.seen:
                found.append((doctor, slot))

    if found:
        send(format_slots(found, now, title))
        for doctor, slot in found:
            state.seen[slot_key(doctor, slot)] = slot.when.isoformat(timespec="minutes")
        changed = True

    for key, when in list(state.seen.items()):
        if datetime.fromisoformat(when) < now:
            del state.seen[key]
            changed = True

    changed |= update_health(state, problems, send)

    summary = ", ".join(f"{k}×{v}" for k, v in sorted(states.items()))
    log(f"{now:%Y-%m-%d %H:%M:%S} {summary}" + (f" | NOWE: {len(found)}" if found else ""))
    return changed


def load_doctors(session, cfg):
    clinic = fetch_clinic(session, cfg.clinic_url)
    doctors, missing = select_doctors(clinic, cfg)
    if not doctors:
        raise ClinicError(
            f"Żaden lekarz w placówce {clinic.name} nie pasuje do konfiguracji "
            "(sprawdź doctors/specialties, listę pokaże: terminator-nfz doctors)."
        )
    return clinic, doctors, missing


def watch(cfg, state_path, send, minutes=None, once=False, verbose=False):
    """Pętla sprawdzania. minutes=None oznacza pracę bez końca. Zwraca kod wyjścia procesu."""
    session = make_session()
    state = State.load(state_path)

    def log(msg):
        if verbose or not msg.startswith("  "):
            print(msg, flush=True)

    try:
        clinic, doctors, missing = load_doctors(session, cfg)
    except ClinicError:
        raise
    except Exception as exc:  # strona placówki chwilowo niedostępna
        print(f"Nie udało się pobrać strony placówki: {exc}", flush=True)
        if update_health(state, [f"Strona placówki niedostępna: {exc}"], send):
            state.save(state_path, now_local())
        return 1

    print(f"{clinic.name}: pilnuję {len(doctors)} lekarzy: " + ", ".join(d.name for d in doctors), flush=True)
    for doc_id in missing:
        print(f"UWAGA: lekarza o id {doc_id} nie ma na stronie placówki", flush=True)

    def fetch(doctor):
        time.sleep(config.DELAY_BETWEEN_DOCTORS_S)
        return fetch_tile(session, doctor)

    deadline = None if minutes is None else time.monotonic() + minutes * 60
    next_refresh = time.monotonic() + config.CLINIC_REFRESH_MINUTES * 60
    while True:
        if time.monotonic() >= next_refresh:
            try:
                clinic, doctors, missing = load_doctors(session, cfg)
            except Exception as exc:  # zostajemy przy poprzedniej liście lekarzy
                print(f"Nie udało się odświeżyć listy lekarzy: {exc}", flush=True)
            next_refresh = time.monotonic() + config.CLINIC_REFRESH_MINUTES * 60
        problems = [f"Lekarza o id {i} nie ma na stronie placówki" for i in missing]
        try:
            if run_round(doctors, fetch, state, send, now_local(), cfg.kinds, clinic.name, problems, log):
                state.save(state_path, now_local())
        except Exception as exc:  # np. Telegram chwilowo niedostępny – spróbujemy w następnej rundzie
            print(f"Błąd rundy: {exc!r}", flush=True)
        if once or (deadline is not None and time.monotonic() + cfg.interval_seconds > deadline):
            break
        time.sleep(cfg.interval_seconds)

    if state.saved_at is None or now_local() - state.saved_at > timedelta(days=config.KEEPALIVE_DAYS):
        state.save(state_path, now_local())
    return 0
