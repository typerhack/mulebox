"""Static checks on install.sh. It is never run for real here."""

import os
import re
import shutil
import subprocess

import pytest

from .helpers import INSTALL_SH, call_install_function

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


def test_install_prints_git_and_venv_hints_for_both_systems():
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "sudo apt-get install python3-venv" in text
    assert "sudo apt-get install git" in text
    assert "xcode-select --install" in text and "brew install python" in text


def test_the_services_are_left_to_mulebox_itself():
    """Units and agents, lingering and the summary of what runs: mulebox/services/, tested there."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert '"$BIN" service install --config "$NODE_TOML"' in text
    for step in ("daemon-reload", "enable", "systemctl --user restart", "launchctl", "loginctl"):
        assert step not in text


def fake_python(folder, name, minor):
    tool = folder / name
    tool.write_text(f"#!/bin/sh\n# {name}: Python 3.{minor}\n"
                    f"case \"$2\" in *3,\\ 12*) [ {minor} -ge 12 ] && exit 0; exit 1;; esac\n"
                    f"echo 3.{minor}\n")
    tool.chmod(0o755)


@pytest.mark.parametrize("found, picked", [
    ({"python3": 9, "python3.13": 13}, "python3.13"),  # a Mac's own python3 and Homebrew's
    ({"python3": 12, "python3.13": 13}, "python3"),
    ({"python3": 9}, "python3"),  # nothing newer: check_python then says what to install
])
def test_an_old_python3_gives_way_to_a_newer_python3_n(tmp_path, found, picked):
    """Only the fakes are on PATH: a machine's own python3.12 in /usr/bin must not count."""
    for name, minor in found.items():
        fake_python(tmp_path, name, minor)
    uname = tmp_path / "uname"
    uname.write_text("#!/bin/sh\necho Linux\n")
    uname.chmod(0o755)
    env = {**os.environ, "PATH": str(tmp_path)}
    env.pop("MULEBOX_PYTHON", None)
    done = subprocess.run(["/bin/bash", "-c", 'source "$1"; pick_python; echo "$PYTHON"', "t",
                           str(INSTALL_SH)], capture_output=True, text=True, env=env, check=True)
    assert done.stdout.strip() == picked


def test_mulebox_python_is_never_second_guessed(tmp_path):
    fake_python(tmp_path, "python3.13", 13)
    env = {**os.environ, "PATH": f"{tmp_path}:/usr/bin:/bin", "MULEBOX_PYTHON": "python3.9"}
    done = subprocess.run(["bash", "-c", 'source "$1"; pick_python; echo "$PYTHON"', "t",
                           str(INSTALL_SH)], capture_output=True, text=True, env=env, check=True)
    assert done.stdout.strip() == "python3.9"


@pytest.mark.parametrize("system, ok", [("Linux", None), ("Darwin", None), ("FreeBSD", False)])
def test_the_platform_check_takes_linux_and_macos(tmp_path, system, ok):
    """With stand-ins for uname, systemctl and git, only the system's own branch runs."""
    for name, body in (("uname", f"echo {system}"), ("systemctl", "exit 0"), ("git", "exit 0")):
        tool = tmp_path / name
        tool.write_text(f"#!/bin/sh\n{body}\n")
        tool.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:/usr/bin:/bin"}
    done = subprocess.run(["bash", "-c", 'source "$1"; check_platform', "t", str(INSTALL_SH)],
                          capture_output=True, text=True, env=env, check=False)
    assert (done.returncode == 0) == (ok is None), done.stderr
    if ok is False:
        assert "nodes run Linux or macOS (found FreeBSD)" in done.stderr


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
