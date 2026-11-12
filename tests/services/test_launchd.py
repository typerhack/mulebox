import plistlib
import subprocess
from pathlib import Path

import pytest

from mulebox.services.base import MISSING, RUNNING, STOPPED, ServiceError
from mulebox.services.launchd import LaunchdServices, definition, search_path


class FakeLaunchd:
    """launchctl as far as mulebox uses it: domains, loaded agents, enable and disable."""

    def __init__(self, gui: bool = True) -> None:
        self.gui = gui
        self.loaded: set[str] = set()
        self.disabled: set[str] = set()
        self.calls: list[list[str]] = []

    def __call__(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        assert argv[0] == "launchctl"
        verb, args = argv[1], argv[2:]
        code, out = 0, ""
        if verb == "print":
            target = args[0]
            if target.count("/") == 1:
                code = 0 if self.gui or target.startswith("user/") else 113
            else:
                label = target.split("/")[-1]
                code, out = (0, "\tstate = running\n") if label in self.loaded else (113, "")
        elif verb == "bootout":
            self.loaded.discard(args[0].split("/")[-1])
        elif verb == "bootstrap":
            label = plistlib.loads(Path(args[1]).read_bytes())["Label"]
            if label in self.disabled or label in self.loaded:
                code, out = 5, "Bootstrap failed: 5: Input/output error"
            else:
                self.loaded.add(label)
        elif verb == "enable":
            self.disabled.discard(args[0].split("/")[-1])
        elif verb == "disable":
            self.disabled.add(args[0].split("/")[-1])
        elif verb == "kickstart":
            code = 0 if args[-1].split("/")[-1] in self.loaded else 113
        return subprocess.CompletedProcess(argv, code, out, out if code else "")


def services(tmp_path, fake, **kw):
    return LaunchdServices(home=tmp_path, run=fake, uid=501, path="/usr/bin:/custom/bin",
                           sleep=lambda s: None, **kw)


def test_the_definition_runs_the_service_and_restarts_it_only_on_failure(tmp_path):
    plist = definition("worker", Path("/Users/alice"), "/usr/bin")
    assert plist["Label"] == "mulebox-worker"
    assert plist["ProgramArguments"] == ["/Users/alice/.mulebox/bin/mulebox", "worker", "serve"]
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert plist["RunAtLoad"] is True
    assert plist["StandardOutPath"] == "/Users/alice/Library/Logs/mulebox/worker.log"
    assert plist["EnvironmentVariables"]["PYTHONUNBUFFERED"] == "1"
    assert "Nice" not in plist and definition("dashboard", Path("/x"), "")["Nice"] == 10


def test_the_path_puts_homebrew_and_mulebox_first_and_keeps_the_rest_once(tmp_path):
    path = search_path(Path("/Users/alice"), "/usr/bin:/custom/bin:/usr/bin")
    parts = path.split(":")
    assert parts[0] == "/Users/alice/.local/bin"
    assert parts.index("/opt/homebrew/bin") < parts.index("/usr/bin")
    assert parts[-1] == "/custom/bin" and parts.count("/usr/bin") == 1


def test_install_writes_and_starts_only_what_the_roles_run(tmp_path):
    fake = FakeLaunchd()
    said = []
    services(tmp_path, fake).install(["worker"], said.append)
    agents = tmp_path / "Library" / "LaunchAgents"
    assert sorted(p.name for p in agents.iterdir()) == ["mulebox-worker.plist"]
    assert fake.loaded == {"mulebox-worker"}
    assert said == ["Started mulebox-worker (gui/501)."]
    assert (tmp_path / "Library" / "Logs" / "mulebox").is_dir()


def test_a_second_install_reloads_the_new_definition(tmp_path):
    fake = FakeLaunchd()
    manager = services(tmp_path, fake)
    manager.install(["coordinator", "worker"], lambda _: None)
    said = []
    manager.install(["coordinator", "worker"], said.append)
    assert fake.loaded == {"mulebox-coordinator", "mulebox-dashboard", "mulebox-worker"}
    assert said[0] == "Restarted mulebox-coordinator (gui/501)."
    verbs = [c[1] for c in fake.calls if c[1] in ("bootout", "bootstrap")]
    assert verbs.count("bootout") == 3 and verbs.count("bootstrap") == 6


def test_a_role_the_node_no_longer_has_is_stopped_and_disabled(tmp_path):
    fake = FakeLaunchd()
    manager = services(tmp_path, fake)
    manager.install(["coordinator", "worker"], lambda _: None)
    manager.install(["worker"], lambda _: None)
    assert fake.loaded == {"mulebox-worker"}
    assert {"mulebox-coordinator", "mulebox-dashboard"} <= fake.disabled
    assert manager.state("coordinator") == STOPPED  # its file stays, nothing is deleted


def test_without_a_screen_login_the_agents_go_to_the_user_domain(tmp_path):
    fake = FakeLaunchd(gui=False)
    manager = services(tmp_path, fake)
    said = []
    manager.install(["worker"], said.append)
    assert said == ["Started mulebox-worker (user/501)."]
    assert ["launchctl", "bootstrap", "user/501",
            str(tmp_path / "Library/LaunchAgents/mulebox-worker.plist")] in fake.calls


def test_state_restart_and_stop(tmp_path):
    fake = FakeLaunchd()
    manager = services(tmp_path, fake)
    assert manager.state("worker") == MISSING
    with pytest.raises(ServiceError, match="not installed"):
        manager.restart("worker")
    manager.install(["worker"], lambda _: None)
    assert manager.state("worker") == RUNNING
    manager.restart("worker")
    assert ["launchctl", "kickstart", "-k", "gui/501/mulebox-worker"] in fake.calls
    manager.stop("worker")
    assert manager.state("worker") == STOPPED and "mulebox-worker" in fake.disabled
    manager.restart("worker")  # a stopped service starts again
    assert manager.state("worker") == RUNNING


def test_an_agent_that_does_not_stop_is_an_error(tmp_path):
    fake = FakeLaunchd()
    manager = services(tmp_path, fake, clock=iter(range(0, 100, 5)).__next__)
    manager.install(["worker"], lambda _: None)
    fake.loaded.add("mulebox-worker")
    original = fake.__call__

    def stuck(argv):
        if argv[1] == "bootout":
            fake.calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")
        return original(argv)

    manager._run = stuck
    with pytest.raises(ServiceError, match="did not stop"):
        manager.stop("worker")


def test_logs_read_the_files_launchd_writes(tmp_path):
    manager = services(tmp_path, FakeLaunchd())
    assert manager.logs_argv(["worker"], follow=True) == [
        "tail", "-n", "200", "-F", str(tmp_path / "Library/Logs/mulebox/worker.log")]


def test_detach_starts_a_session_of_its_own(tmp_path):
    started = []
    manager = services(tmp_path, FakeLaunchd(), spawn=lambda argv, **kw: started.append((argv, kw)))
    manager.detach("mulebox-upgrade-j1", ["mulebox", "upgrade-wait", "J1"])
    argv, kw = started[0]
    assert argv == ["mulebox", "upgrade-wait", "J1"] and kw["start_new_session"] is True
    with pytest.raises(ServiceError, match="refusing"):
        manager.detach("other", ["true"])


def test_unknown_service_names_are_refused(tmp_path):
    with pytest.raises(ServiceError, match="no mulebox service"):
        services(tmp_path, FakeLaunchd()).restart("sshd")


def test_the_boot_note_names_automatic_login(tmp_path):
    assert "automatic login" in services(tmp_path, FakeLaunchd()).boot_note()
