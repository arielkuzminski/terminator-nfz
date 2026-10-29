from pathlib import Path

import pytest

from terminator_nfz.clinic import ClinicError, parse_clinic_page, select_doctors
from terminator_nfz.config import Config

FIXTURES = Path(__file__).parent / "fixtures"
CLINIC_URL = "https://lekarzebezkolejki.pl/PrzychodniaMedycynaPolskaSp.ZO.O.Krakow"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def clinic():
    return parse_clinic_page(load("clinic_page.html"), CLINIC_URL)


def test_parses_clinic_name_and_all_doctors(clinic):
    assert clinic.name == "Przychodnia Medycyna Polska"
    assert len(clinic.doctors) == 8
    doctor = next(d for d in clinic.doctors if d.id == "1173880")
    assert doctor.name == "Piotr Hortmanowicz"
    assert doctor.description == "lekarz medycyny ogólnej"
    assert doctor.unit == "PORADNIA (GABINET) LEKARZA POZ"
    assert doctor.provider_id == "927612"
    assert doctor.rzoz_id == "-49793"
    assert doctor.unit_no == "1"
    assert doctor.specialty_id == "3081"
    assert doctor.path == "/piotr-hortmanowicz/lekarz-rodzinny/krakow"
    assert doctor.slug == "piotr-hortmanowicz"
    assert doctor.location == "krakow"
    assert doctor.url == "https://lekarzebezkolejki.pl/piotr-hortmanowicz/lekarz-rodzinny/krakow"


def test_parses_large_clinic():
    clinic = parse_clinic_page(load("clinic_page_large.html"), "https://lekarzebezkolejki.pl/CentrumMedycznePolmedS.A.Krakow-Srodmiescie")
    assert clinic.name == "Centrum Medyczne POLMED Kraków"
    assert len(clinic.doctors) == 67
    assert {d.unit_no for d in clinic.doctors} == {"551"}
    assert all(d.path.startswith("/") and d.slug and d.location for d in clinic.doctors)


def test_clinic_without_online_registration():
    with pytest.raises(ClinicError, match="rejestracją online"):
        parse_clinic_page(load("clinic_page_no_online.html"), "https://lekarzebezkolejki.pl/x")


def test_select_by_doctor_ids(clinic):
    cfg = Config(clinic_url=CLINIC_URL, doctors=["1173760", "1173780", "999"])
    chosen, missing = select_doctors(clinic, cfg)
    assert {d.name for d in chosen} == {"Michał Konrad Chowaniec", "Rafał Michał Idzikowski"}
    assert missing == ["999"]


def test_select_by_specialty(clinic):
    cfg = Config(clinic_url=CLINIC_URL, specialties=["3081"])
    chosen, missing = select_doctors(clinic, cfg)
    assert len(chosen) == 7
    assert missing == []


def test_select_all_when_no_filters(clinic):
    chosen, _ = select_doctors(clinic, Config(clinic_url=CLINIC_URL))
    assert len(chosen) == 8
