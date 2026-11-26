"""An upgrade on trial (install.sh: trial_services, undo_on_failure; venv.sh: roll_back). Real
venvs in a temporary home, with a stand-in `mulebox` in each that records what it was asked."""

import os
import subprocess
import sys

from .helpers import INSTALL_SH

FAKE = """#!/bin/sh
echo "{name} $*" >> "$HOME/calls"
case "$1" in
  --version) echo "mulebox {name}" ;;
  service) [ "$2" = trial ] && exit {trial} ;;
esac
exit 0
"""


def upgrade(home, trial_exit, previous=True, then="trial_services 0"):
    """A first install with mulebox 'old', then an upgrade to 'new' whose trial exits so."""
    first = ("new_venv; swap_venv; fake old 0; " if previous else "")
    script = (
        'source "$1"; '
        'fake() { printf "%s" "$(printf "$FAKE" | sed "s/{name}/$1/g; s/{trial}/$2/")" '
        '> "$NEW_VENV/bin/mulebox"; chmod +x "$NEW_VENV/bin/mulebox"; }; '
        f"{first}sleep 1; new_venv; swap_venv; fake new {trial_exit}; "
        f"trap undo_on_failure EXIT; {then}; SWAPPED=''")
    env = {**os.environ, "HOME": str(home), "MULEBOX_PYTHON": sys.executable, "FAKE": FAKE,
           "MULEBOX_TRIAL_S": "1"}
    done = subprocess.run(["bash", "-c", script, "t", str(INSTALL_SH)], capture_output=True,
                          text=True, env=env, check=False)
    calls = (home / "calls").read_text().splitlines() if (home / "calls").exists() else []
    return done, os.readlink(home / ".mulebox" / "venv"), calls


def venvs(home):
    return sorted(p.name for p in (home / ".mulebox" / "venvs").iterdir())


def test_an_upgrade_that_holds_stays(tmp_path):
    done, link, calls = upgrade(tmp_path, 0)
    assert done.returncode == 0, done.stderr
    assert link == f"venvs/{venvs(tmp_path)[1]}"  # the new one
    assert any(c.startswith("new service trial --config") and "--seconds 1" in c for c in calls)


def test_an_upgrade_that_does_not_hold_goes_back_and_restarts_the_old_services(tmp_path):
    done, link, calls = upgrade(tmp_path, 1)
    assert done.returncode == 1
    assert link == f"venvs/{venvs(tmp_path)[0]}"  # the one before
    assert calls[-1].startswith("old service install --config")
    assert f"went back to mulebox old, in {link}" in done.stderr
    assert "the upgrade was undone; the version before runs again" in done.stderr


def test_any_failure_once_the_new_venv_is_in_use_goes_back(tmp_path):
    done, link, _ = upgrade(tmp_path, 0, then="false")
    assert done.returncode == 1 and link == f"venvs/{venvs(tmp_path)[0]}"


def test_a_first_install_has_no_trial_and_nothing_to_go_back_to(tmp_path):
    done, link, calls = upgrade(tmp_path, 1, previous=False)
    assert done.returncode == 0 and not any("trial" in c for c in calls)
    again = tmp_path / "again"
    again.mkdir()
    done, _, _ = upgrade(again, 0, previous=False, then="false")
    assert done.returncode == 1 and "no earlier version to go back to" in done.stderr
