"""An upgrade on trial (services/trial.py), and how each manager tells one run of a service from
the next (`instance`)."""

from mulebox.services import trial
from mulebox.services.base import RUNNING
from mulebox.services.launchd import LaunchdServices
from mulebox.services.systemd import SystemdServices

from .fake_commands import FakeCommands

SINCE = 1_000_000.0


class Manager:
    """Services whose runs change on a timetable: {name: [(from_s, instance or None), ...]}."""

    def __init__(self, plan, clock):
        self.plan, self.clock = plan, clock

    def state(self, name):
        return RUNNING if self.instance(name) else "stopped"

    def instance(self, name):
        now = [run for at, run in self.plan[name] if at <= self.clock.t]
        return now[-1] if now else None


class Clock:
    t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def run(plan, contact=lambda: {"version": "2.0.0", "at": SINCE + 3}, seconds=60):
    clock = Clock()
    return trial.run(Manager(plan, clock), list(plan), SINCE, "2.0.0", contact, seconds=seconds,
                     sleep=clock.sleep, clock=clock, wall=lambda: SINCE + clock.t)


def test_services_that_hold_and_a_worker_that_reached_its_coordinator_pass():
    assert run({"coordinator": [(0, "a")], "worker": [(0, "b")]}) is None


def test_a_service_that_stops_or_restarts_fails_it_and_says_when():
    assert run({"worker": [(0, "b"), (20, None)]}) == \
        "the worker service stopped 20 s after the upgrade"
    assert "the coordinator service restarted (it crashed" in run(
        {"coordinator": [(0, "a"), (40, "a2")]})


def test_a_service_not_running_at_all_fails_at_once():
    assert run({"dashboard": []}) == "the dashboard service is not running after the upgrade"


def test_a_worker_that_never_reached_its_coordinator_fails_at_the_end():
    plan = {"worker": [(0, "b")]}
    for said in (None, {"version": "1.9.0", "at": SINCE + 3}, {"version": "2.0.0", "at": SINCE - 30}):
        assert run(plan, contact=lambda said=said: said) == \
            "the worker did not reach its coordinator within 60 s of the upgrade"


def test_a_node_without_a_worker_needs_no_contact():
    assert run({"coordinator": [(0, "a")]}, contact=None) is None


def test_systemd_gives_the_invocation_id_of_a_running_unit(tmp_path):
    units = tmp_path / ".config/systemd/user"
    units.mkdir(parents=True)
    (units / "mulebox-worker.service").write_text("")
    fake = FakeCommands(lambda argv: (0, "6f1c2e\n") if "InvocationID" in argv else None)
    assert SystemdServices(home=tmp_path, run=fake).instance("worker") == "6f1c2e"
    stopped = FakeCommands(lambda argv: (3, "") if "is-active" in argv else None)
    assert SystemdServices(home=tmp_path, run=stopped).instance("worker") is None


def test_launchd_gives_the_pid_of_a_loaded_agent(tmp_path, monkeypatch):
    manager = LaunchdServices(home=tmp_path, run=FakeCommands(), uid=501, path="/usr/bin",
                              sleep=lambda s: None)
    monkeypatch.setattr(manager, "_loaded", lambda lbl: "\tstate = running\n\tpid = 4242\n")
    assert manager.instance("worker") == "4242"
    monkeypatch.setattr(manager, "_loaded", lambda lbl: "\tstate = not running\n")
    assert manager.instance("worker") is None
