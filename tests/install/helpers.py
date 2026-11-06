"""Shared paths and a helper that calls one function from mulebox/machine/install.sh."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_DIR = REPO_ROOT / "mulebox" / "machine"
INSTALL_SH = INSTALL_DIR / "install.sh"
UNIT_DIR = INSTALL_DIR / "systemd"


def call_install_function(name: str, *args: str, env: dict | None = None) -> str:
    """Source install.sh (main does not run when sourced) and call one function."""
    script = f'source "$1"; shift; {name} "$@"'
    done = subprocess.run(
        ["bash", "-c", script, "install-test", str(INSTALL_SH), *args],
        capture_output=True, text=True, check=True, env=env,
    )
    return done.stdout
