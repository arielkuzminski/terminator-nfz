"""Stałe serwisu i plik konfiguracyjny użytkownika (config.toml)."""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

BASE_URL = "https://lekarzebezkolejki.pl"
TILE_PATH = "/placowkaMedyczna/pobierzKafelWizytowkiAjax"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)
TIMEOUT_S = 20
DELAY_BETWEEN_DOCTORS_S = 0.5
MIN_INTERVAL_S = 30
# Po ilu kolejnych nieudanych rundach wysłać ostrzeżenie na Telegram.
FAIL_ALERT_ROUNDS = 3
# Jak często odświeżać listę lekarzy placówki w długiej pętli.
CLINIC_REFRESH_MINUTES = 60
# Zapisz stan co najmniej raz na tyle dni (GitHub wyłącza cron po 60 dniach bezczynności publicznego repo).
KEEPALIVE_DAYS = 25
TIMEZONE = "Europe/Warsaw"

# Nazwa w config.toml -> klasa CSS boksu na stronie.
VISIT_TYPES = {"nfz": "nfz", "prywatna": "prv"}


class ConfigError(Exception):
    pass


@dataclass
class Config:
    clinic_url: str
    doctors: list = field(default_factory=list)  # idZasobu lekarzy; pusta lista = bez filtra
    specialties: list = field(default_factory=list)  # idSpecjalnosciRZOZ; pusta lista = bez filtra
    visit_types: list = field(default_factory=lambda: ["nfz"])
    interval_seconds: float = 90

    @property
    def kinds(self):
        return tuple(VISIT_TYPES[v] for v in self.visit_types)


def normalize_clinic_url(url):
    parts = urlsplit(url.strip())
    if parts.netloc and parts.netloc not in ("lekarzebezkolejki.pl", "www.lekarzebezkolejki.pl"):
        raise ConfigError(f"clinic_url musi wskazywać stronę placówki na lekarzebezkolejki.pl, a jest: {url}")
    if not parts.path or parts.path == "/":
        raise ConfigError("clinic_url nie wskazuje konkretnej placówki")
    return BASE_URL + parts.path.rstrip("/")


def _ids(value, name):
    if not isinstance(value, list):
        raise ConfigError(f"{name} musi być listą, np. {name} = [1234567, 2345678]")
    return [str(v).strip() for v in value]


def load_config(path):
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Brak pliku {path}. Uruchom `terminator-nfz setup` albo skopiuj config.example.toml do config.toml.")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Błąd składni TOML w {path}: {exc}") from exc

    unknown = set(data) - {"clinic_url", "doctors", "specialties", "visit_types", "interval_seconds"}
    if unknown:
        raise ConfigError(f"Nieznane pola w {path}: {', '.join(sorted(unknown))}")
    if not data.get("clinic_url"):
        raise ConfigError(f"Brak clinic_url w {path}")

    visit_types = data.get("visit_types", ["nfz"])
    if not visit_types or any(v not in VISIT_TYPES for v in visit_types):
        raise ConfigError(f"visit_types może zawierać tylko: {', '.join(VISIT_TYPES)}")

    interval = data.get("interval_seconds", 90)
    if not isinstance(interval, (int, float)) or interval < MIN_INTERVAL_S:
        raise ConfigError(f"interval_seconds musi wynosić co najmniej {MIN_INTERVAL_S}")

    return Config(
        clinic_url=normalize_clinic_url(data["clinic_url"]),
        doctors=_ids(data.get("doctors", []), "doctors"),
        specialties=_ids(data.get("specialties", []), "specialties"),
        visit_types=list(visit_types),
        interval_seconds=interval,
    )
