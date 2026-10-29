"""Zapytania HTTP do lekarzebezkolejki.pl."""

import requests

from . import config
from .clinic import parse_clinic_page


def make_session():
    session = requests.Session()
    session.headers.update({"User-Agent": config.USER_AGENT})
    return session


def fetch_clinic(session, url):
    resp = session.get(url, timeout=config.TIMEOUT_S)
    resp.raise_for_status()
    return parse_clinic_page(resp.text, url)


def fetch_tile(session, doctor):
    params = {
        "idZasobu": doctor.id,
        "idSwiadczeniodawcy": doctor.provider_id,
        "idKafla": doctor.tile_selector,  # bez tego parametru serwer zwraca stronę błędu
        "typZasobu": "L",
        "idSwiadczeniodawcyRZOZ": doctor.rzoz_id,
        "idSpecjalnosciRZOZ": doctor.specialty_id,
        "nrJednostki": doctor.unit_no,
        "czyGrupowanie": "true",
        "czyRejestracjaBezKarty": "true",
        "typWidoku": "LBK-WIZ",
        "backLink": "",
        "rejestracjaUrlTerminarz": doctor.path,
        "linkZasobu": doctor.slug,
        "linkLokalizacji": doctor.location,
        "linkSpecjalnosci": "",
        "czyIntegracjaLBK": "true",
        "skierowanieType": "REF_BRAK",
        "pokazDemo": "false",
    }
    resp = session.get(
        config.BASE_URL + config.TILE_PATH,
        params=params,
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=config.TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.text
