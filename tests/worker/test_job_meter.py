"""Whether one job is doing anything; nothing here reads a real control group."""

import threading

from mulebox.worker import cgroups, job_meter
from mulebox.worker.job_meter import SAMPLE_S, ContainerList, JobMeter

STAT = "usage_usec 2500000\nuser_usec 1\nsystem_usec 1\n"
NET = "x\ny\n  lo: 500 0 0 0 0 0 0 0 500 0 0 0 0 0 0 0\n eth0: 1000 0 0 0 0 0 0 0 24 0 0 0 0 0 0 0\n"


def judged(before, after):
    values = iter((before, after))
    meter = JobMeter(lambda: next(values))
    meter.update(0.0)
    meter.update(SAMPLE_S)
    return meter


def is_busy(before, after):
    return judged(before, after).busy_at == SAMPLE_S


def test_a_sleeping_job_is_idle_from_the_first_span():
    assert judged({"unit": 1.0}, {"unit": 1.001}).busy_at == 0.0


def test_a_percent_of_a_core_in_the_job_itself_is_activity():
    assert is_busy({"unit": 0.0}, {"unit": SAMPLE_S * 0.01})


def test_an_idle_database_is_no_activity():
    assert not is_busy({"unit": 0.0, "service:a": 5.0},
                       {"unit": 0.0, "service:a": 5.0 + SAMPLE_S * 0.07})  # 7% of a core


def test_a_busy_service_is_activity():
    assert is_busy({"unit": 0.0, "service:a": 0.0}, {"unit": 0.0, "service:a": SAMPLE_S * 0.5})


def test_services_add_up():
    before = {"unit": 0.0, "service:a": 0.0, "service:b": 0.0}
    assert is_busy(before, {"unit": 0.0, "service:a": SAMPLE_S * 0.06,
                              "service:b": SAMPLE_S * 0.06})


def test_a_services_traffic_is_activity():
    assert is_busy({"unit": 0.0, "net:a": 0.0}, {"unit": 0.0, "net:a": 1024.0 * 120})


def test_a_service_that_appears_started_at_zero_and_one_that_left_counts_nothing():
    assert is_busy({"unit": 0.0}, {"unit": 0.0, "service:a": 20.0})
    assert not is_busy({"unit": 0.0, "service:a": 90.0}, {"unit": 0.0})


def test_job_cpu_is_reported_as_share_of_a_core():
    assert judged({"unit": 0.0}, {"unit": SAMPLE_S * 0.5}).cpu_pct == 50.0


def test_a_failed_read_forgets_what_was_known():
    values = iter(({"unit": 0.0}, {"unit": 30.0}, None))
    meter = JobMeter(lambda: next(values))
    for at in (0.0, SAMPLE_S, SAMPLE_S * 2):
        meter.update(at)
    assert meter.busy_at is None and meter.cpu_pct is None


def test_samples_only_every_so_often_even_when_reads_fail():
    calls = []
    meter = JobMeter(lambda: calls.append(1))
    for at in (0.0, 1.0, 2.0, SAMPLE_S, SAMPLE_S + 1):
        meter.update(at)
    assert len(calls) == 2


def test_cpu_seconds_from_a_group(tmp_path):
    (tmp_path / "cpu.stat").write_text(STAT)
    assert cgroups.cpu_seconds(tmp_path) == 2.5
    assert cgroups.cpu_seconds(tmp_path / "gone") is None


def test_a_containers_group_with_either_docker_driver(tmp_path):
    systemd = tmp_path / "system.slice" / "docker-abc.scope"
    systemd.mkdir(parents=True)
    plain = tmp_path / "docker" / "def"
    plain.mkdir(parents=True)
    assert cgroups.container_group("abc", tmp_path) == systemd
    assert cgroups.container_group("def", tmp_path) == plain
    assert cgroups.container_group("ghi", tmp_path) is None


def test_a_containers_traffic_leaves_out_loopback(tmp_path):
    (tmp_path / "cgroup.procs").write_text("42\n43\n")
    (tmp_path / "42" / "net").mkdir(parents=True)
    (tmp_path / "42" / "net" / "dev").write_text(NET)
    assert cgroups.group_net_bytes(tmp_path, tmp_path) == 1024


def test_no_process_in_the_group_is_no_reading(tmp_path):
    (tmp_path / "cgroup.procs").write_text("")
    assert cgroups.group_net_bytes(tmp_path, tmp_path) is None


class Daemon:
    def __init__(self):
        self.release = threading.Event()
        self.release.set()
        self.failing = False

    def lines(self, *args, **kwargs):
        self.release.wait(5)
        if self.failing:
            raise OSError("no daemon")
        return ["abc"]


def settled(containers):
    containers._task.wait(5)


def test_containers_arrive_on_the_next_look():
    containers = ContainerList(Daemon(), "job-1")
    assert containers.ids() is None
    settled(containers)
    assert containers.ids() == ["abc"]
    settled(containers)


def test_a_stuck_daemon_reads_unknown_and_asks_once():
    daemon = Daemon()
    daemon.release.clear()
    containers = ContainerList(daemon, "job-1")
    assert containers.ids() is None
    task = containers._task
    assert containers.ids() is None and containers._task is task
    daemon.release.set()
    settled(containers)


def test_a_failed_listing_reads_unknown():
    daemon = Daemon()
    daemon.failing = True
    containers = ContainerList(daemon, "job-1")
    containers.ids()
    settled(containers)
    assert containers.ids() is None
    settled(containers)


def test_a_job_with_an_unread_unit_is_unknown(monkeypatch):
    monkeypatch.setattr(cgroups, "cpu_seconds", lambda group: None)
    assert job_meter.read_job("job-1", None) is None


def test_a_reading_has_the_unit_and_each_container(monkeypatch, tmp_path):
    monkeypatch.setattr(cgroups, "cpu_seconds", lambda group: 3.0)
    monkeypatch.setattr(cgroups, "container_group", lambda name: tmp_path)
    monkeypatch.setattr(cgroups, "group_net_bytes", lambda group: 7)

    class Known:
        def ids(self):
            return ["abc"]

    assert job_meter.read_job("job-1", Known()) == {"unit": 3.0, "service:abc": 3.0, "net:abc": 7.0}
