"""Okienkowa wersja: gdzie trzymać pliki, autostart z Windowsem, jedna kopia programu, brak uśpienia."""

import os
import sys
from pathlib import Path

APP_NAME = "TerminatorNFZ"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LOG_KEEP_LINES = 500

IS_WINDOWS = sys.platform == "win32"


def data_dir():
    """%APPDATA%\\TerminatorNFZ na Windows, ~/.config/terminator-nfz gdzie indziej."""
    if IS_WINDOWS and os.environ.get("APPDATA"):
        path = Path(os.environ["APPDATA"]) / APP_NAME
    else:
        path = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "terminator-nfz"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path():
    return data_dir() / "config.toml"


def state_path():
    return data_dir() / "state.json"


def env_path():
    return data_dir() / ".env"


def log_path():
    return data_dir() / "log.txt"


def append_log(line, path=None, keep=LOG_KEEP_LINES):
    """Dopisuje linię do log.txt, zostawiając tylko ostatnie `keep` linii."""
    path = Path(path or log_path())
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines.append(line)
    path.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")


def autostart_command():
    """Polecenie dla wpisu autostartu: sam .exe albo pythonw z modułem, gdy program działa z Pythona."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --autostart'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    python = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{python}" -m terminator_nfz.gui --autostart'


def autostart_enabled(name=APP_NAME):
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, name)
        return True
    except FileNotFoundError:
        return False


def set_autostart(enabled, command=None, name=APP_NAME):
    """Wpis w HKCU\\...\\Run – działa bez uprawnień administratora."""
    if not IS_WINDOWS:
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command or autostart_command())
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass


def single_instance(name=APP_NAME):
    """True, gdy to jedyna działająca kopia programu. Uchwyt mutexa żyje do końca procesu."""
    if not IS_WINDOWS:
        return True
    import ctypes

    ERROR_ALREADY_EXISTS = 183
    kernel32 = ctypes.windll.kernel32
    single_instance.handle = kernel32.CreateMutexW(None, False, f"Local\\{name}")
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def keep_awake(on):
    """Nie pozwala Windowsowi uśpić komputera, dopóki pilnujemy terminów (ekran może zgasnąć)."""
    if not IS_WINDOWS:
        return
    import ctypes

    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
    ctypes.windll.kernel32.SetThreadExecutionState(flags)
