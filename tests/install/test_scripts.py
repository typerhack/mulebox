"""Static checks on install.sh and deploy.sh. Neither script is ever run for real here."""

import os
import re
import shutil
import subprocess

import pytest

from .helpers import DEPLOY_SH, INSTALL_SH, UNIT_DIR

SCRIPTS = [INSTALL_SH, DEPLOY_SH]
# A command position: line start, or after ; & | ( ` or a shell keyword.
COMMAND_START = r"(?:^|[;&|(`]|\bthen|\bdo|\belse)\s*"


def code_lines(path):
    """Lines without full-line comments (heredoc Python included, which is fine here)."""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.lstrip().startswith("#"):
            yield number, line


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_bash_syntax(script):
    subprocess.run(["bash", "-n", str(script)], check=True)


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_shellcheck(script):
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not installed")
    subprocess.run(["shellcheck", "-x", str(script)], check=True)


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_strict_mode_and_executable(script):
    assert "set -euo pipefail" in script.read_text(encoding="utf-8")
    assert os.access(script, os.X_OK)


def test_install_never_uses_sudo():
    pattern = re.compile(COMMAND_START + r"sudo\b")
    bad = [n for n, line in code_lines(INSTALL_SH) if pattern.search(line)]
    assert bad == [], f"sudo used as a command on lines {bad}"


def test_install_never_removes_directories():
    recursive = re.compile(r"\brm\s+(?:-\S*\s+)*-\S*[rR]|\brm\b.*--recursive|\brmdir\b")
    bad = [n for n, line in code_lines(INSTALL_SH) if recursive.search(line)]
    assert bad == [], f"recursive delete on lines {bad}"


def test_install_rm_only_on_exact_files():
    rm = re.compile(COMMAND_START + r"rm\b(.*)")
    for number, line in code_lines(INSTALL_SH):
        match = rm.search(line)
        if match:
            assert re.fullmatch(r' -f "\$[a-z_]+"', match.group(1)), f"line {number}: {line}"


def test_install_prints_venv_and_linger_hints():
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "sudo apt-get install python3-venv" in text
    assert "sudo loginctl enable-linger" in text
    assert 'loginctl show-user "$user" -p Linger' in text


def test_install_ships_every_unit_it_names():
    text = INSTALL_SH.read_text(encoding="utf-8")
    for unit in UNIT_DIR.glob("*.service"):
        assert unit.name in text


@pytest.fixture
def stub_path(tmp_path):
    """PATH where ssh and scp only record that they were called."""
    log = tmp_path / "calls.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("ssh", "scp"):
        stub = bin_dir / tool
        stub.write_text(f'#!/bin/sh\necho "{tool} $*" >> "{log}"\nexit 99\n')
        stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    return env, log


@pytest.mark.parametrize(
    "args", [[], ["-oProxyCommand=x"], ["-"], ["bad host"], ["host:path"], ["a", "b"]]
)
def test_deploy_rejects_bad_targets_before_any_ssh(stub_path, args):
    env, log = stub_path
    done = subprocess.run(["bash", str(DEPLOY_SH), *args], env=env, capture_output=True)
    assert done.returncode != 0
    assert not log.exists()
