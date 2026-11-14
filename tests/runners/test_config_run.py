"""The runner's config.sh as mulebox runs it (runners/manage.py, run_config)."""

import os
import time

import pytest

from mulebox.runners import manage


def test_a_hung_config_is_stopped_with_everything_it_started(tmp_path, monkeypatch):
    """config.sh starts `Runner.Listener`; killing only the script left that running (seen on
    a Mac node), so the whole group goes, and the error says what it printed last."""
    monkeypatch.setattr(manage, "CONFIG_TIMEOUT_S", 1)
    script = tmp_path / "config.sh"
    script.write_text("#!/bin/sh\necho '# Authentication'\nsleep 60 &\necho $! > child\nwait\n")
    script.chmod(0o755)
    with pytest.raises(manage.RunnerError) as info:
        manage.run_config([str(script), "--unattended"], tmp_path, dict(os.environ))
    assert "did not finish within 1 s" in str(info.value) and "# Authentication" in str(info.value)
    child = int((tmp_path / "child").read_text())
    for _ in range(50):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail("the child of config.sh is still running")


def test_a_finished_config_gives_its_exit_and_output(tmp_path):
    script = tmp_path / "config.sh"
    script.write_text("#!/bin/sh\necho done\nexit 3\n")
    script.chmod(0o755)
    proc = manage.run_config([str(script), "remove"], tmp_path, dict(os.environ))
    assert proc.returncode == 3 and proc.stdout.strip() == "done"
