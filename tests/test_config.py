import pytest

from terminator_nfz.config import ConfigError, load_config


def write(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_full_config(tmp_path):
    cfg = load_config(write(tmp_path, """
clinic_url = "https://lekarzebezkolejki.pl/PrzychodniaMedycynaPolskaSp.ZO.O.Krakow?ls=x"
doctors = [1173760, "1173780"]
specialties = [3081]
visit_types = ["nfz", "prywatna"]
interval_seconds = 120
"""))
    assert cfg.clinic_url == "https://lekarzebezkolejki.pl/PrzychodniaMedycynaPolskaSp.ZO.O.Krakow"
    assert cfg.doctors == ["1173760", "1173780"]
    assert cfg.specialties == ["3081"]
    assert cfg.kinds == ("nfz", "prv")
    assert cfg.interval_seconds == 120


def test_defaults_and_path_only_url(tmp_path):
    cfg = load_config(write(tmp_path, 'clinic_url = "/PrzychodniaMedycynaPolskaSp.ZO.O.Krakow"'))
    assert cfg.clinic_url == "https://lekarzebezkolejki.pl/PrzychodniaMedycynaPolskaSp.ZO.O.Krakow"
    assert cfg.doctors == [] and cfg.kinds == ("nfz",) and cfg.interval_seconds == 90


@pytest.mark.parametrize("text, message", [
    ("", "clinic_url"),
    ('clinic_url = "https://example.com/x"', "lekarzebezkolejki.pl"),
    ('clinic_url = "/x"\nvisit_types = ["vip"]', "visit_types"),
    ('clinic_url = "/x"\ninterval_seconds = 5', "interval_seconds"),
    ('clinic_url = "/x"\ndoktors = [1]', "doktors"),
    ("clinic_url = ", "TOML"),
])
def test_invalid_config(tmp_path, text, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write(tmp_path, text))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="config.example.toml"):
        load_config(tmp_path / "config.toml")
