#!/usr/bin/env python3
"""Build the downloadable client: dist/mulebox-<version>-<os>-<arch>.tar.gz.

Run from a venv with `pip install '.[binary]'`. It is a folder, not one file: PyInstaller's
single file unpacks itself on every start, measured at 10 s on macOS against 0.2 s for the folder,
and agents run mulebox all day. The package's own files go in as data, so `mulebox setup` can
build the wheel a build machine needs (client/wheel.py).
"""

import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_SYSTEMS = {"darwin": "macos", "linux": "linux"}
_MACHINES = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x86_64", "amd64": "x86_64"}


def archive_name(version: str, system: str, machine: str) -> str:
    return (f"mulebox-{version}-{_SYSTEMS[system.lower()]}-"
            f"{_MACHINES[machine.lower()]}.tar.gz")


def main() -> int:
    version = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    out = REPO / "dist"
    out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mulebox-binary-") as folder:
        work = Path(folder)
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--log-level", "ERROR", "--onedir",
            "--name", "mulebox", "--distpath", str(work / "dist"),
            "--workpath", str(work / "build"), "--specpath", str(work),
            "--copy-metadata", "mulebox", "--collect-submodules", "mulebox",
            "--add-data", f"{REPO / 'mulebox'}:mulebox",
            str(REPO / "mulebox" / "__main__.py"),
        ], check=True)
        target = out / archive_name(version, platform.system(), platform.machine())
        with tarfile.open(target, "w:gz") as tar:
            tar.add(work / "dist" / "mulebox", "mulebox")
    shutil.rmtree(REPO / "build", ignore_errors=True)
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
