"""Strona placówki: nazwa i lekarze z parametrami potrzebnymi do pobrania ich terminów."""

import re
from dataclasses import dataclass
from urllib.parse import unquote

from bs4 import BeautifulSoup

from .config import BASE_URL


class ClinicError(Exception):
    pass


@dataclass(frozen=True)
class Doctor:
    id: str  # idZasobu
    name: str
    description: str  # np. "lekarz medycyny ogólnej"
    unit: str  # poradnia, np. "PORADNIA (GABINET) LEKARZA POZ"
    provider_id: str  # idSwiadczeniodawcy
    rzoz_id: str  # idSwiadczeniodawcyRZOZ
    unit_no: str  # nrJednostki
    specialty_id: str  # idSpecjalnosciRZOZ, np. 3081 = POZ
    tile_selector: str  # idKafla
    path: str  # rejestracjaUrlTerminarz, np. /placowka/jan-kowalski/lekarz-rodzinny/miasto
    slug: str  # linkZasobu
    location: str  # linkLokalizacji

    @property
    def key(self):
        return f"{self.id}-{self.specialty_id}"

    @property
    def url(self):
        return BASE_URL + self.path


@dataclass
class Clinic:
    name: str
    url: str
    doctors: list


# Strona placówki ładuje kafelek każdego lekarza wywołaniem:
# ladujKafleWizytowki(idZasobu, idSwiadczeniodawcy, "idKafla", 'L', idSwiadczeniodawcyRZOZ, 'nrJednostki',
#                     'idSpecjalnosciRZOZ', ..., 'rejestracjaUrlTerminarz', 'linkZasobu', 'linkLokalizacji', ...);
CALL_RE = re.compile(
    r"ladujKafleWizytowki\(\s*(\d+)\s*,\s*(\d+)\s*,\s*\"([^\"]*)\"\s*,\s*'L'\s*,\s*(-?\d+)\s*,\s*'([^']*)'\s*,"
    r"\s*'(\d+)'.*?null\s*,\s*'(?:true|false)'\s*,\s*'(/[^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'",
    re.S,
)


def _text(el):
    return " ".join(el.get_text(" ").split()) if el else ""


def parse_clinic_page(html, url):
    soup = BeautifulSoup(html, "html.parser")
    name = _text(soup.title).removesuffix("- LekarzeBezKolejki.pl").strip() or url
    doctors = {}
    for m in CALL_RE.finditer(html):
        doc_id, provider_id, selector, rzoz_id, unit_no, specialty_id, path, slug, location = m.groups()
        link = soup.find("a", id=f"linkNazwaZasobu_{doc_id}_{rzoz_id}_{specialty_id}")
        article = link.find_parent("article") if link else None
        unit = re.search(rf" {doc_id} (.*?) XXX_", unquote(selector))
        doctor = Doctor(
            id=doc_id,
            name=_text(link) or slug,
            description=_text(article.select_one(".thd-desc")) if article else "",
            unit=" ".join(unit.group(1).split()) if unit else "",
            provider_id=provider_id,
            rzoz_id=rzoz_id,
            unit_no=unit_no,
            specialty_id=specialty_id,
            tile_selector=selector,
            path=path,
            slug=slug,
            location=location,
        )
        doctors.setdefault(doctor.key, doctor)
    if not doctors:
        raise ClinicError(
            f"Na stronie {url} nie ma lekarzy z rejestracją online. Sprawdź adres albo wybierz placówkę, "
            "która udostępnia terminy przez lekarzebezkolejki.pl."
        )
    return Clinic(name, url, list(doctors.values()))


def select_doctors(clinic, cfg):
    """Lekarze pasujący do konfiguracji oraz lista idZasobu z konfiguracji, których nie ma na stronie."""
    chosen = [
        d for d in clinic.doctors
        if (not cfg.doctors or d.id in cfg.doctors) and (not cfg.specialties or d.specialty_id in cfg.specialties)
    ]
    found = {d.id for d in clinic.doctors}
    missing = [i for i in cfg.doctors if i not in found]
    return chosen, missing
