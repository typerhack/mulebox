"""A runner job's CPU, from its service's control group and its compose containers."""

from pathlib import Path

from mulebox.runners import runner_meter
from mulebox.runners.runner_meter import CiContainers, RunnerMeter, runner_containers
from mulebox.worker import cgroups

ROOT = Path("/home/alice/.mulebox/runners")


def test_cpu_is_unknown_first_then_the_share_of_a_core_since_the_last_reading():
    used = iter([{"runner": 10.0}, {"runner": 13.0}, None])
    meter = RunnerMeter(read=lambda runner: next(used))
    assert meter.cpu_pct("job-1", "build-1-app", 100.0) is None  # nothing to compare yet
    assert meter.cpu_pct("job-1", "build-1-app", 110.0) == 30.0
    assert meter.cpu_pct("job-1", "build-1-app", 120.0) is None  # unreadable: unknown, not 0


def test_containers_count_from_their_second_reading_and_a_gone_one_adds_nothing():
    used = iter([{"runner": 10.0, "db": 100.0},
                 {"runner": 11.0, "db": 160.0, "api": 500.0},  # api just seen: not yet counted
                 {"runner": 12.0, "api": 520.0}])  # db removed
    meter = RunnerMeter(read=lambda runner: next(used))
    assert meter.cpu_pct("job-1", "build-1-app", 0.0) is None
    assert meter.cpu_pct("job-1", "build-1-app", 10.0) == 610.0
    assert meter.cpu_pct("job-1", "build-1-app", 20.0) == 210.0


def test_a_runners_containers_are_those_started_inside_its_work_folder():
    lines = [f"aaa\t{ROOT}/build-1-app/_work/app/app",
             f"bbb\t{ROOT}/build-1-app/_work/app/app/infra",
             f"ccc\t{ROOT}/build-1-other/_work/other/other",
             f"ddd\t{ROOT}/build-1-app/mulebox-hooks",  # not a job's folder
             f"eee\t{ROOT}/build-1-app/_work/../../../../elsewhere",
             "fff\t/home/alice/projects/app",  # started by hand
             "ggg\t", "\t/x"]  # plain `docker run`, and a malformed line
    assert runner_containers(lines, ROOT) == {"build-1-app": ["aaa", "bbb"],
                                              "build-1-other": ["ccc"]}


def test_the_last_known_containers_are_kept_while_docker_is_late(monkeypatch):
    class Docker:
        def lines(self, *args):
            assert "--format" in args
            return [f"aaa\t{ROOT}/build-1-app/_work/app/app"]

    containers = CiContainers(ROOT, Docker())
    answers = iter([None, {"build-1-app": ["aaa"]}, None])
    monkeypatch.setattr(containers._polled, "value", lambda: next(answers))
    containers.refresh()
    assert containers.of("build-1-app") == []
    containers.refresh()
    containers.refresh()  # late: the last answer stays
    assert containers.of("build-1-app") == ["aaa"]


def test_a_reading_adds_the_containers_to_the_runner_service(tmp_path, monkeypatch):
    groups = {"runner": tmp_path / "runner", "aaa": tmp_path / "aaa"}
    monkeypatch.setattr(runner_meter.cgroups, "runner_group", lambda runner: groups["runner"])
    monkeypatch.setattr(runner_meter.cgroups, "container_group", lambda c: groups.get(c))
    monkeypatch.setattr(runner_meter.cgroups, "cpu_seconds",
                        lambda group: {groups["runner"]: 2.0, groups["aaa"]: 7.5}[group])

    class Known:
        def of(self, runner):
            return ["aaa", "gone"]

    assert runner_meter.runner_reading("build-1-app", Known()) == {"runner": 2.0, "aaa": 7.5}


def test_a_runner_service_is_found_in_its_template_slice(tmp_path, monkeypatch):
    monkeypatch.setattr(cgroups.os, "getuid", lambda: 1000)
    apps = tmp_path / "user.slice/user-1000.slice/user@1000.service/app.slice"
    group = apps / "app-mulebox\\x2drunner.slice" / "mulebox-runner@build-1-app.service"
    group.mkdir(parents=True)
    (group / "cpu.stat").write_text("usage_usec 2500000\nuser_usec 1\n")
    assert cgroups.runner_group("build-1-app", tmp_path) == group
    assert cgroups.cpu_seconds(group) == 2.5
    assert cgroups.runner_group("build-1-other", tmp_path) is None


def test_an_isolated_runner_is_read_from_its_container(tmp_path, monkeypatch):
    from mulebox.runners import runner_meter

    (tmp_path / "ci").mkdir()
    (tmp_path / "ci" / ".mulebox-place").write_text("mulebox-place-ci-abcd1234\n")
    asked = []

    class Docker:
        def run(self, *args):
            asked.append(args)
            return "f00d\n"

    groups = {"f00d": tmp_path / "group"}
    monkeypatch.setattr(runner_meter.cgroups, "runner_group", lambda runner: None)
    monkeypatch.setattr(runner_meter.cgroups, "container_group", lambda cid: groups.get(cid))
    monkeypatch.setattr(runner_meter.cgroups, "cpu_seconds", lambda group: 12.5)
    places = runner_meter.PlaceGroups(tmp_path, Docker())
    assert runner_meter.runner_reading("ci", None, places) == {"runner": 12.5}
    assert runner_meter.runner_reading("ci", None, places) == {"runner": 12.5}
    assert len(asked) == 1  # the id is asked once per container
    assert runner_meter.runner_reading("other", None, places) is None
