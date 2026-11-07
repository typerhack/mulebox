"""A runner job's CPU, from its service's control group."""

from mulebox.runners.runner_meter import RunnerMeter
from mulebox.worker import cgroups


def test_cpu_is_unknown_first_then_the_share_of_a_core_since_the_last_reading():
    used = iter([10.0, 13.0, None])
    meter = RunnerMeter(read=lambda runner: next(used))
    assert meter.cpu_pct("job-1", "build-1-app", 100.0) is None  # nothing to compare yet
    assert meter.cpu_pct("job-1", "build-1-app", 110.0) == 30.0
    assert meter.cpu_pct("job-1", "build-1-app", 120.0) is None  # unreadable: unknown, not 0


def test_a_runner_service_is_found_in_its_template_slice(tmp_path, monkeypatch):
    monkeypatch.setattr(cgroups.os, "getuid", lambda: 1000)
    apps = tmp_path / "user.slice/user-1000.slice/user@1000.service/app.slice"
    group = apps / "app-mulebox\\x2drunner.slice" / "mulebox-runner@build-1-app.service"
    group.mkdir(parents=True)
    (group / "cpu.stat").write_text("usage_usec 2500000\nuser_usec 1\n")
    assert cgroups.runner_group("build-1-app", tmp_path) == group
    assert cgroups.cpu_seconds(group) == 2.5
    assert cgroups.runner_group("build-1-other", tmp_path) is None
