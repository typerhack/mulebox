import pytest

from mulebox import cli
from mulebox.services import commands, manager
from mulebox.services.base import RUNNING, ServiceError


class Recorder:
    kind = "fake"

    def __init__(self):
        self.done = []

    def install(self, roles, say):
        self.done.append(("install", tuple(roles)))
        say("Started mulebox-worker.")

    def restart(self, name):
        self.done.append(("restart", name))

    def stop(self, name):
        self.done.append(("stop", name))

    def state(self, name):
        return RUNNING

    def logs_argv(self, names, follow):
        return ["tail", *names]

    def boot_note(self):
        return "log in once"


@pytest.fixture
def fake(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(commands, "for_platform", lambda: recorder)
    return recorder


def node_toml(tmp_path, roles='["worker"]'):
    path = tmp_path / "node.toml"
    path.write_text(f'name = "build-1"\nroles = {roles}\ncoordinator = "build-0"\n'
                    f'[roots]\njobs = "{tmp_path}/j"\nprojects = "{tmp_path}/p"\n'
                    f'cache = "{tmp_path}/c"\nstaging = "{tmp_path}/s"\nrunners = "{tmp_path}/r"\n'
                    '[dashboard]\nmode = "off"\n')
    return path


def test_install_reads_the_roles_and_says_what_runs(tmp_path, fake, capsys):
    assert cli.main(["service", "install", "--config", str(node_toml(tmp_path))]) == 0
    assert fake.done == [("install", ("worker",))]
    out = capsys.readouterr().out
    assert "service:  worker (running)" in out
    assert "Logs: mulebox service logs worker" in out and "log in once" in out


def test_restart_and_stop_take_several_names_in_order(fake):
    assert cli.main(["service", "restart", "coordinator", "worker"]) == 0
    assert cli.main(["service", "stop", "dashboard"]) == 0
    assert fake.done == [("restart", "coordinator"), ("restart", "worker"), ("stop", "dashboard")]


def test_status_lists_every_service(fake, capsys):
    assert cli.main(["service", "status"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "coordinator\trunning", "dashboard\trunning", "worker\trunning"]
    assert cli.main(["service", "status", "sshd"]) == 1


def test_an_error_is_one_line_and_exit_1(fake, capsys, monkeypatch):
    def broken(name):
        raise ServiceError("launchctl said no")
    monkeypatch.setattr(fake, "restart", broken)
    assert cli.main(["service", "restart", "worker"]) == 1
    assert "mulebox service: error: launchctl said no" in capsys.readouterr().err


def test_the_platform_picks_the_manager():
    assert manager.for_platform("linux").kind == "systemd"
    assert manager.for_platform("darwin").kind == "launchd"
    with pytest.raises(ServiceError, match="Linux or macOS"):
        manager.for_platform("win32")
