import sys

import pytest

from terminator_nfz import appdata


def test_data_dir_uses_appdata_on_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(appdata, "IS_WINDOWS", True)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert appdata.data_dir() == tmp_path / "TerminatorNFZ"
    assert appdata.config_path() == tmp_path / "TerminatorNFZ" / "config.toml"
    assert (tmp_path / "TerminatorNFZ").is_dir()


def test_data_dir_elsewhere(tmp_path, monkeypatch):
    monkeypatch.setattr(appdata, "IS_WINDOWS", False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert appdata.data_dir() == tmp_path / "terminator-nfz"


def test_log_keeps_last_lines(tmp_path):
    log = tmp_path / "log.txt"
    for i in range(5):
        appdata.append_log(f"linia {i}", path=log, keep=3)

    assert log.read_text(encoding="utf-8").splitlines() == ["linia 2", "linia 3", "linia 4"]


@pytest.mark.skipif(sys.platform != "win32", reason="rejestr Windows")
def test_autostart_roundtrip():
    name = "TerminatorNFZ-pytest"
    try:
        appdata.set_autostart(True, '"C:\\x\\TerminatorNFZ.exe" --autostart', name=name)
        assert appdata.autostart_enabled(name)
    finally:
        appdata.set_autostart(False, name=name)
    assert not appdata.autostart_enabled(name)
    appdata.set_autostart(False, name=name)  # usunięcie nieistniejącego wpisu nie jest błędem
