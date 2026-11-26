"""An install builds a venv of its own and swaps it in with one rename (install.sh: new_venv,
swap_venv, prune_venvs), so a power cut at any moment leaves a whole mulebox. Run with a real
Python's venv in a temporary home; pip installs nothing here."""

import os
import subprocess
import sys

from .helpers import INSTALL_SH


def steps(home, *names, env_extra=None):
    """Source install.sh and run these functions in one shell, as main would."""
    script = 'source "$1"; ' + "; ".join(names)
    env = {**os.environ, "HOME": str(home), "MULEBOX_PYTHON": sys.executable, **(env_extra or {})}
    done = subprocess.run(["bash", "-c", script, "t", str(INSTALL_SH)], capture_output=True,
                          text=True, env=env, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout


def link(home):
    return os.readlink(home / ".mulebox" / "venv")


def test_a_first_install_puts_a_new_venv_behind_the_link(tmp_path):
    out = steps(tmp_path, "new_venv", "swap_venv")
    assert "Created" in out
    target = link(tmp_path)
    assert target.startswith("venvs/") and (tmp_path / ".mulebox" / target / "bin" / "python").exists()
    assert os.readlink(tmp_path / ".mulebox" / "bin" / "mulebox") == str(
        tmp_path / ".mulebox" / "venv" / "bin" / "mulebox")


def test_an_upgrade_copies_the_venv_in_use_and_swaps_the_link(tmp_path):
    steps(tmp_path, "new_venv", "swap_venv")
    first = link(tmp_path)
    (tmp_path / ".mulebox" / first / "marker").write_text("from the first")
    out = steps(tmp_path, "sleep 1", "new_venv", "swap_venv")
    second = link(tmp_path)
    assert "Copied the venv in use" in out and second != first
    assert (tmp_path / ".mulebox" / second / "marker").read_text() == "from the first"
    assert (tmp_path / ".mulebox" / first).is_dir()  # the old one stays until pruned


def test_a_venv_from_before_is_moved_once_and_kept_as_the_previous(tmp_path):
    old = tmp_path / ".mulebox" / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(old)], check=True)
    steps(tmp_path, "new_venv", "swap_venv", "prune_venvs")
    names = sorted(p.name for p in (tmp_path / ".mulebox" / "venvs").iterdir())
    assert len(names) == 2 and any(n.endswith("-old") for n in names)
    assert os.path.islink(old)


def test_prune_keeps_the_venv_in_use_and_the_one_before(tmp_path):
    for _ in range(3):
        steps(tmp_path, "sleep 1", "new_venv", "swap_venv", "prune_venvs")
    venvs = tmp_path / ".mulebox" / "venvs"
    (venvs / "not-ours").mkdir()
    names = sorted(p.name for p in venvs.iterdir())
    assert len(names) == 3 and "not-ours" in names
    assert link(tmp_path) == f"venvs/{names[1]}"  # the newest of the two stamps


def test_a_failed_install_leaves_the_venv_in_use(tmp_path):
    steps(tmp_path, "new_venv", "swap_venv")
    before = link(tmp_path)
    script = 'source "$1"; new_venv; install_wheel /nowhere/mulebox-9.9.9-py3-none-any.whl'
    env = {**os.environ, "HOME": str(tmp_path), "MULEBOX_PYTHON": sys.executable}
    done = subprocess.run(["bash", "-c", script, "t", str(INSTALL_SH)], capture_output=True,
                          text=True, env=env, check=False)
    assert done.returncode != 0 and link(tmp_path) == before
