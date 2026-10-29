"""Parsowanie kafelka z terminami lekarza (fragment HTML z pobierzKafelWizytowkiAjax)."""

import re
from dataclasses import dataclass, field
from datetime import datetime

from bs4 import BeautifulSoup

FREE = "FREE"
FULL = "FULL"
NOT_PUBLISHED = "NOT_PUBLISHED"
UNKNOWN = "UNKNOWN"

MONTHS = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6,
    "lipca": 7, "sierpnia": 8, "września": 9, "października": 10, "listopada": 11, "grudnia": 12,
}
KIND_CLASSES = {"t-nfz": "nfz", "t-prv": "prv"}


@dataclass(frozen=True)
class Slot:
    kind: str  # "nfz" albo "prv"
    label: str  # np. "Wizyta NFZ"
    when: datetime  # czas lokalny (Europe/Warsaw), bez strefy
    booking_path: str  # np. "/logowanie/XR1k..." – rezerwacja tego konkretnego terminu


@dataclass
class TileStatus:
    state: str
    slots: list = field(default_factory=list)
    note: str = ""


def _text(el):
    return " ".join(el.get_text(" ").split()) if el else ""


def _parse_when(link):
    date_text = _text(link.select_one(".tb-data"))
    time_text = _text(link.select_one(".tb-time"))
    d = re.fullmatch(r"(\d{1,2}) (\w+) (\d{4})", date_text)
    t = re.fullmatch(r"(\d{1,2}):(\d{2})", time_text)
    if not d or not t or d.group(2) not in MONTHS:
        return None
    return datetime(int(d.group(3)), MONTHS[d.group(2)], int(d.group(1)), int(t.group(1)), int(t.group(2)))


def parse_tile(html, kinds=("nfz",)):
    """Zwraca stan terminów dla wybranych rodzajów wizyt (domyślnie tylko NFZ).

    Wszystko, czego nie rozpoznajemy, daje UNKNOWN, żeby zmiana strony nie wyglądała jak „brak terminów”.
    """
    soup = BeautifulSoup(html, "html.parser")
    slots, notes, unrecognised = [], [], False
    boxes = 0

    for box in soup.select("div.termin-box"):
        kind = next((KIND_CLASSES[c] for c in box.get("class", []) if c in KIND_CLASSES), None)
        if kind not in kinds:
            continue
        boxes += 1
        label = _text(box.select_one(".tb-lead"))
        link = box.select_one("a.tb-link")
        none = box.select_one(".tb-none")
        if link:
            when = _parse_when(link)
            if when is None:
                unrecognised = True
                continue
            slots.append(Slot(kind, label, when, link.get("href", "")))
        elif none:
            notes.append(f"{label}: {_text(none)}")
        else:
            unrecognised = True

    note = " | ".join(notes)
    if slots:
        return TileStatus(FREE, sorted(set(slots), key=lambda s: s.when), note)
    if boxes == 0 or unrecognised:
        return TileStatus(UNKNOWN, [], note or _text(soup)[:200])
    # „Zajęte są wszystkie udostępnione… terminy do dnia …” albo „W tej chwili brak wolnych terminów…”
    if any("Zajęte" in n or "brak wolnych terminów" in n for n in notes):
        return TileStatus(FULL, [], note)
    if all("nie udostępnia" in n for n in notes):
        return TileStatus(NOT_PUBLISHED, [], note)
    return TileStatus(UNKNOWN, [], note)
