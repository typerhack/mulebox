"""Static checks on install.sh. It is never run for real here."""

import os
import re
import shutil
import subprocess

import pytest

from .helpers import INSTALL_SH, UNIT_DIR, call_install_function

SCRIPTS = [INSTALL_SH]
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


def test_install_prints_git_venv_and_linger_hints():
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "sudo apt-get install python3-venv" in text
    assert "sudo apt-get install git" in text
    assert "sudo loginctl enable-linger" in text
    assert 'loginctl show-user "$user" -p Linger' in text


def test_install_ships_every_unit_it_names():
    text = INSTALL_SH.read_text(encoding="utf-8")
    for unit in UNIT_DIR.glob("*.service"):
        assert unit.name in text


def test_the_command_is_linked_on_the_path(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path)}
    call_install_function("link_on_path", env=env)
    link = tmp_path / ".local" / "bin" / "mulebox"
    assert os.readlink(link) == str(tmp_path / ".mulebox" / "bin" / "mulebox")


def test_a_real_file_of_that_name_stays(tmp_path):
    link = tmp_path / ".local" / "bin" / "mulebox"
    link.parent.mkdir(parents=True)
    link.write_text("mine")
    out = call_install_function("link_on_path", env={**os.environ, "HOME": str(tmp_path)})
    assert link.read_text() == "mine" and "left alone" in out
