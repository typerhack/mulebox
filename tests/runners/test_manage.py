"""Runner add / list / remove on the node, with fake config.sh and systemctl."""

import logging
import os

import pytest

from mulebox.runners import layout, manage
from mulebox.runners.manage import RunnerError
from mulebox.runners.names import RunnerUsageError

from .conftest import TOKEN

REPO = "example-org/example-app"
NAME = "build-1-example-app"


def add(machine, **kw):
    return manage.add(machine, REPO, TOKEN, name=kw.get("name", NAME),
                      labels=kw.get("labels", ("mulebox",)))


def test_config_argv_has_no_token(paths):
    folder = paths.runners / NAME
    argv = manage.config_argv(folder, REPO, NAME, ("mulebox", "gpu"))
    assert argv == [str(folder / "config.sh"), "--unattended",
                    "--url", "https://github.com/example-org/example-app",
                    "--name", NAME, "--labels", "mulebox,gpu", "--work", "_work", "--replace"]
    assert manage.remove_argv(folder) == [str(folder / "config.sh"), "remove"]


def test_add_registers_writes_hooks_and_starts_the_unit(machine, fakes, paths):
    folder = add(machine)
    assert folder == paths.runners / NAME
    assert (folder / "run.sh").is_file()
    [(argv, cwd, env)] = fakes.configs
    assert cwd == folder and argv == manage.config_argv(folder, REPO, NAME, ("mulebox",))
    assert env["ACTIONS_RUNNER_INPUT_TOKEN"] == TOKEN
    assert all(TOKEN not in arg for arg in argv)
    assert fakes.systemctl_calls == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", f"mulebox-runner@{NAME}.service"],
    ]


def test_hook_scripts_and_env_lines(machine):
    folder = add(machine)
    hooks = folder / "mulebox-hooks"
    for kind in ("started", "completed"):
        script = hooks / f"{kind}.sh"
        assert f'"$HOME/.mulebox/bin/mulebox" runner-hook {kind}' in script.read_text()
        assert os.stat(script).st_mode & 0o100
    assert "kill -9" in (hooks / "started.sh").read_text()  # fails closed
    lines = (folder / ".env").read_text().splitlines()
    assert lines == ["LANG=C.UTF-8",
                     f"ACTIONS_RUNNER_HOOK_JOB_STARTED={hooks / 'started.sh'}",
                     f"ACTIONS_RUNNER_HOOK_JOB_COMPLETED={hooks / 'completed.sh'}"]
    assert layout.read_meta(folder)["repo"] == REPO
    assert layout.read_meta(folder)["actors"] == []


def test_add_keeps_the_accounts_it_runs_for(machine):
    folder = manage.add(machine, REPO, TOKEN, name=NAME, labels=("mulebox",), actors=("alice",))
    assert layout.read_meta(folder)["actors"] == ["alice"]


def test_token_never_in_output_logs_or_errors(machine, fakes, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    fakes.config_result = (1, f"Http response code: Unauthorized for token {TOKEN}\n", "")
    with pytest.raises(RunnerError) as info:
        add(machine)
    text = str(info.value)
    assert "Unauthorized" in text and "[redacted]" in text
    assert TOKEN not in text and TOKEN not in repr(info.value.__cause__)
    assert TOKEN not in caplog.text
    assert TOKEN not in " ".join(fakes.said) + "".join(capsys.readouterr())


def test_failed_config_removes_the_runner_folder(machine, fakes, paths):
    fakes.config_result = (1, "", "boom")
    with pytest.raises(RunnerError, match="boom"):
        add(machine)
    assert not (paths.runners / NAME).exists()
    assert [p.name for p in paths.runners.iterdir()] == []
    assert fakes.systemctl_calls == []


def test_existing_runner_refused(machine, paths, fakes):
    (paths.runners / NAME).mkdir()
    with pytest.raises(RunnerUsageError, match="already exists"):
        add(machine)
    assert fakes.downloads == []


def test_bad_token_refused_without_echo(machine):
    with pytest.raises(RunnerUsageError) as info:
        manage.add(machine, REPO, "two words", name=NAME, labels=("mulebox",))
    assert "two words" not in str(info.value)


def test_runners_root_must_match_the_unit_template(machine, tmp_path):
    machine.home = tmp_path / "elsewhere"
    with pytest.raises(RunnerUsageError, match="roots.runners"):
        add(machine)


def test_missing_unit_template_refused(machine, home):
    (home / ".config" / "systemd" / "user" / "mulebox-runner@.service").unlink()
    with pytest.raises(RunnerError, match="rerun the mulebox installer"):
        add(machine)


def test_systemctl_failure_keeps_the_registered_runner(machine, fakes, paths):
    fakes.systemctl_codes["enable"] = 1
    with pytest.raises(RunnerError, match="registered"):
        add(machine)
    assert (paths.runners / NAME / ".runner").exists()


def test_list_shows_service_state_and_busy(machine, paths):
    add(machine)
    (paths.runners / NAME / layout.RESERVATION_FILE).write_text("job_x")
    (paths.runners / ".tmp-leftover").mkdir()
    [row] = manage.list_runners(machine)
    assert (row.name, row.repo, row.state, row.busy) == (NAME, REPO, "active", True)


def test_find_by_repo(machine):
    add(machine)
    assert manage.find_by_repo(machine, REPO) == NAME
    with pytest.raises(RunnerUsageError, match="no runner"):
        manage.find_by_repo(machine, "example-org/other")
    with pytest.raises(RunnerUsageError, match="belongs to"):
        manage.check_runner_repo(machine, NAME, "example-org/other")


def test_remove_stops_unregisters_and_deletes_through_safepath(machine, fakes, paths,
                                                               monkeypatch):
    add(machine)
    fakes.systemctl_calls.clear()
    removed = []
    real = manage.remove_tree
    monkeypatch.setattr(manage, "remove_tree",
                        lambda path, roots: removed.append((path, roots)) or real(path, roots))
    manage.remove(machine, NAME, TOKEN)
    assert fakes.systemctl_calls == [
        ["systemctl", "--user", "disable", "--now", f"mulebox-runner@{NAME}.service"],
        ["systemctl", "--user", "reset-failed", f"mulebox-runner@{NAME}.service"]]
    argv, _, env = fakes.configs[-1]
    assert argv == manage.remove_argv(paths.runners / NAME)
    assert env["ACTIONS_RUNNER_INPUT_TOKEN"] == TOKEN
    assert removed == [(paths.runners / NAME, paths.roots)]
    assert not (paths.runners / NAME).exists()


def test_remove_keeps_files_when_github_refuses(machine, fakes, paths):
    add(machine)
    fakes.config_result = (1, f"bad token {TOKEN}", "")
    with pytest.raises(RunnerError) as info:
        manage.remove(machine, NAME, TOKEN)
    assert TOKEN not in str(info.value)
    assert (paths.runners / NAME).is_dir()


def test_remove_refuses_a_symlinked_runner(machine, paths, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    (paths.runners / "evil").symlink_to(outside)
    with pytest.raises(RunnerUsageError):
        manage.remove(machine, "evil", TOKEN)
    assert (outside / "keep.txt").exists()

