import pytest

from mulebox.services.base import MISSING, RUNNING, STOPPED, ServiceError, wanted
from mulebox.services.systemd import SystemdServices, shipped_units

from .fake_commands import FakeCommands


def active(*units):
    return lambda argv: (0 if argv[-1] in units else 3, "") if "is-active" in argv else None


def test_the_roles_decide_the_services():
    assert wanted(["coordinator", "worker"]) == ["coordinator", "dashboard", "worker"]
    assert wanted(["worker"]) == ["worker"]  # the dashboard goes with the coordinator


def test_install_copies_every_unit_and_starts_the_roles(tmp_path):
    fake = FakeCommands(active())
    said = []
    SystemdServices(home=tmp_path, run=fake).install(["worker"], said.append)
    unit_dir = tmp_path / ".config/systemd/user"
    assert sorted(p.name for p in unit_dir.iterdir()) == sorted(shipped_units())
    assert "mulebox-runner@.service" in shipped_units()  # copied, enabled per runner
    assert "systemctl --user daemon-reload" in fake.joined()
    assert "systemctl --user enable --now --quiet mulebox-worker.service" in fake.joined()
    assert not any("coordinator" in call and "enable" in call for call in fake.joined())
    assert said == ["Enabled and started mulebox-worker.service."]


def test_install_restarts_a_running_service_and_sets_runner_shares_in_place(tmp_path):
    def runners(argv):
        if "list-units" in argv:
            return 0, "mulebox-runner@app-1.service loaded active running\n"
        return None
    (tmp_path / ".config/systemd/user").mkdir(parents=True)
    (tmp_path / ".config/systemd/user/mulebox-worker.service").write_text("")
    fake = FakeCommands(runners, active("mulebox-worker.service"))
    said = []
    SystemdServices(home=tmp_path, run=fake).install(["worker"], said.append)
    assert ("systemctl --user set-property --runtime mulebox-runner@app-1.service "
            "CPUWeight=50 IOWeight=50") in fake.joined()
    assert "systemctl --user restart mulebox-worker.service" in fake.joined()
    assert not any("restart mulebox-runner" in call for call in fake.joined())
    assert said == ["Restarted mulebox-worker.service."]


def test_a_failed_step_says_which(tmp_path):
    fake = FakeCommands(lambda argv: (1, "boom") if "daemon-reload" in argv else None)
    with pytest.raises(ServiceError, match="daemon-reload.*boom"):
        SystemdServices(home=tmp_path, run=fake).install(["worker"], lambda _: None)


def test_state_restart_stop_and_logs(tmp_path):
    fake = FakeCommands(active("mulebox-worker.service"))
    manager = SystemdServices(home=tmp_path, run=fake)
    assert manager.state("worker") == MISSING
    (tmp_path / ".config/systemd/user").mkdir(parents=True)
    (tmp_path / ".config/systemd/user/mulebox-worker.service").write_text("")
    (tmp_path / ".config/systemd/user/mulebox-coordinator.service").write_text("")
    assert manager.state("worker") == RUNNING and manager.state("coordinator") == STOPPED
    manager.restart("worker")
    manager.stop("coordinator")
    assert fake.joined()[-2:] == ["systemctl --user restart mulebox-worker.service",
                                  "systemctl --user disable --now mulebox-coordinator.service"]
    assert manager.logs_argv(["worker", "coordinator"], follow=False) == [
        "journalctl", "--user", "-u", "mulebox-worker", "-u", "mulebox-coordinator", "-n", "200"]


def test_detach_is_a_transient_unit(tmp_path):
    fake = FakeCommands()
    SystemdServices(home=tmp_path, run=fake).detach("mulebox-upgrade-j1", ["mulebox", "x"])
    assert fake.joined() == [
        "systemd-run --user --unit=mulebox-upgrade-j1 --collect --quiet mulebox x"]
    with pytest.raises(ServiceError, match="refusing"):
        SystemdServices(home=tmp_path, run=fake).detach("sshd", ["true"])


@pytest.mark.parametrize("linger, enable, note", [
    ("Linger=yes", 0, False), ("Linger=no", 0, False), ("Linger=no", 1, True)])
def test_the_boot_note_is_about_lingering(tmp_path, linger, enable, note):
    fake = FakeCommands(
        lambda argv: (0, linger) if "show-user" in argv else None,
        lambda argv: (enable, "") if "enable-linger" in argv else None)
    got = SystemdServices(home=tmp_path, run=fake).boot_note()
    assert (got is not None) == note
    if note:
        assert "sudo loginctl enable-linger" in got
