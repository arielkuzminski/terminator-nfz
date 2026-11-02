"""Buduje dist/TerminatorNFZ.exe.

Wymaga: pip install ".[gui]" pyinstaller
Użycie:  python packaging/build_exe.py
"""

import subprocess
import sys
from pathlib import Path

from terminator_nfz.icon import save_ico

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"


def main():
    BUILD.mkdir(exist_ok=True)
    icon = BUILD / "TerminatorNFZ.ico"
    save_ico(icon)
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--onefile", "--windowed", "--noupx",
            "--name", "TerminatorNFZ",
            "--icon", str(icon),
            "--collect-submodules", "pystray",
            "--distpath", str(ROOT / "dist"),
            "--workpath", str(BUILD / "pyinstaller"),
            "--specpath", str(BUILD),
            str(ROOT / "packaging" / "launcher.py"),
        ],
        check=True,
        cwd=ROOT,
    )
    print(f"Gotowe: {ROOT / 'dist' / 'TerminatorNFZ.exe'}")


if __name__ == "__main__":
    main()
