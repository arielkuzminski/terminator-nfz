"""Buduje pojedynczy plik wykonywalny w dist/.

    python packaging/build_exe.py gui                    -> dist/TerminatorNFZ.exe (okienkowa, Windows)
    python packaging/build_exe.py cli [--name NAZWA]     -> dist/terminator-nfz[.exe] (terminal, każdy system)

Wymaga: pip install ".[gui]" pyinstaller tzdata   (dla cli wystarczy: pip install . pyinstaller tzdata)
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"


def pyinstaller_args(kind, name):
    common = [
        "--noconfirm", "--clean", "--onefile", "--noupx",
        "--name", name,
        # Baza stref czasowych w środku: Windows i okrojone systemy (np. kontenery) nie mają własnej.
        "--collect-data", "tzdata",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(BUILD / f"pyinstaller-{kind}"),
        "--specpath", str(BUILD),
    ]
    if kind == "gui":
        from terminator_nfz.icon import save_ico

        icon = BUILD / "TerminatorNFZ.ico"
        save_ico(icon)
        return common + ["--windowed", "--icon", str(icon), "--collect-submodules", "pystray",
                         str(ROOT / "packaging" / "launcher.py")]
    return common + ["--console", "--exclude-module", "tkinter", "--exclude-module", "PIL",
                     "--exclude-module", "pystray", str(ROOT / "packaging" / "launcher_cli.py")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["gui", "cli"])
    parser.add_argument("--name", help="nazwa pliku wynikowego (bez .exe)")
    args = parser.parse_args()
    name = args.name or {"gui": "TerminatorNFZ", "cli": "terminator-nfz"}[args.kind]

    BUILD.mkdir(exist_ok=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", *pyinstaller_args(args.kind, name)], check=True, cwd=ROOT)
    suffix = ".exe" if sys.platform == "win32" else ""
    print(f"Gotowe: {ROOT / 'dist' / (name + suffix)}")


if __name__ == "__main__":
    main()
