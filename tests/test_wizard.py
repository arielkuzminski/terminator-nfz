from pathlib import Path

import pytest

from terminator_nfz import wizard
from terminator_nfz.clinic import parse_clinic_page
from terminator_nfz.config import load_config

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://lekarzebezkolejki.pl/PrzychodniaMedycynaPolskaSp.ZO.O.Krakow"
FULL_HTML = (FIXTURES / "tile_full.html").read_text(encoding="utf-8")


class Script:
    """Podaje kolejne odpowiedzi na pytania kreatora i zbiera to, co wypisał."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.output = []

    def ask(self, prompt=""):
        self.output.append(prompt)
        if not self.answers:
            raise AssertionError(f"Kreator zadał nieoczekiwane pytanie: {prompt!r}")
        return self.answers.pop(0)

    def say(self, *parts):
        self.output.append(" ".join(str(p) for p in parts))

    @property
    def text(self):
        return "\n".join(self.output)


@pytest.fixture
def fake_site(monkeypatch):
    clinic = parse_clinic_page((FIXTURES / "clinic_page.html").read_text(encoding="utf-8"), URL)
    calls = {"sent": []}

    def fetch_clinic(_session, url):
        if "zla" in url:
            raise wizard.ClinicError("nie ma lekarzy z rejestracją online")
        return clinic

    monkeypatch.setattr(wizard, "fetch_clinic", fetch_clinic)
    monkeypatch.setattr(wizard, "fetch_tile", lambda _s, _d: FULL_HTML)
    monkeypatch.setattr(wizard.config, "DELAY_BETWEEN_DOCTORS_S", 0)
    monkeypatch.setattr(wizard, "bot_name", lambda token: "MojBot" if token == "123:ok" else None)
    monkeypatch.setattr(wizard, "find_chats", lambda token: [(555, "Jan (private)")])
    monkeypatch.setattr(wizard, "telegram_sender", lambda token, chat_id: lambda text: calls["sent"].append((chat_id, text)))
    return clinic, calls


def number_of(clinic_doctors_order, name):
    return str(next(i for i, d in enumerate(clinic_doctors_order, 1) if d.name == name))


def test_full_setup_writes_config_and_env(tmp_path, fake_site):
    clinic, calls = fake_site
    order = wizard.listing_order(clinic.doctors)
    picks = f"{number_of(order, 'Michał Konrad Chowaniec')}, {number_of(order, 'Rafał Michał Idzikowski')}"
    script = Script([
        "https://lekarzebezkolejki.pl/placowka/zla",  # zła placówka -> pytanie ponownie
        URL,
        "99",  # numer spoza listy -> pytanie ponownie
        picks,
        "",  # rodzaj wizyt: domyślnie NFZ
        "",  # interwał: domyślnie 90
        "t",  # skonfigurować Telegram
        "123:zly",  # zły token -> pytanie ponownie
        "123:ok",
        "",  # Enter po napisaniu do bota
    ])
    config_path, env_path = tmp_path / "config.toml", tmp_path / ".env"

    wizard.run_setup(script.ask, script.ask, script.say, config_path, env_path)

    cfg = load_config(config_path)
    assert cfg.clinic_url == URL
    assert set(cfg.doctors) == {"1173760", "1173780"}
    assert cfg.kinds == ("nfz",)
    assert cfg.interval_seconds == 90
    assert "Michał Konrad Chowaniec" in config_path.read_text(encoding="utf-8")

    env = env_path.read_text(encoding="utf-8")
    assert "TELEGRAM_TOKEN=123:ok" in env
    assert "TELEGRAM_CHAT_ID=555" in env
    assert calls["sent"] and calls["sent"][0][0] == 555
    assert "nie ma lekarzy z rejestracją online" in script.text
    assert "terminator-nfz run" in script.text


def test_existing_files_are_kept_when_user_declines(tmp_path, fake_site):
    config_path, env_path = tmp_path / "config.toml", tmp_path / ".env"
    config_path.write_text("stara konfiguracja", encoding="utf-8")
    env_path.write_text("TELEGRAM_TOKEN=stary\nTELEGRAM_CHAT_ID=1\nINNE=zostaje\n", encoding="utf-8")
    script = Script(["n", "n"])  # nie nadpisuj config.toml, nie zmieniaj Telegrama

    wizard.run_setup(script.ask, script.ask, script.say, config_path, env_path)

    assert config_path.read_text(encoding="utf-8") == "stara konfiguracja"
    assert "INNE=zostaje" in env_path.read_text(encoding="utf-8")


def test_env_update_keeps_other_lines(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("# komentarz\nINNE=1\nTELEGRAM_TOKEN=stary\n", encoding="utf-8")
    wizard.update_env(env_path, {"TELEGRAM_TOKEN": "nowy", "TELEGRAM_CHAT_ID": "7"})
    assert env_path.read_text(encoding="utf-8") == "# komentarz\nINNE=1\nTELEGRAM_TOKEN=nowy\nTELEGRAM_CHAT_ID=7\n"


@pytest.mark.parametrize("text, expected", [
    ("1 3", [1, 3]),
    ("1,3", [1, 3]),
    ("2-4", [2, 3, 4]),
    ("3, 1-2", [3, 1, 2]),
])
def test_parse_numbers(text, expected):
    assert wizard.parse_numbers(text, 5) == expected


@pytest.mark.parametrize("text", ["0", "6", "a", "3-1", ""])
def test_parse_numbers_rejects(text):
    with pytest.raises(ValueError):
        wizard.parse_numbers(text, 5)


@pytest.mark.parametrize("fixture, expected", [
    ("tile_full.html", "NFZ: zajęte"),
    ("tile_not_published.html", "NFZ: —"),
    ("tile_free_nfz.html", "NFZ: od 26.11 17:50"),
    ("tile_free_private.html", "NFZ: — | prywatnie: od 27.11 07:30"),
    ("tile_no_free_now.html", "NFZ: zajęte"),
])
def test_status_summary(fixture, expected):
    assert wizard.status_summary((FIXTURES / fixture).read_text(encoding="utf-8")) == expected
