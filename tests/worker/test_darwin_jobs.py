"""A job's readings on a Mac: its process group from `ps`, its containers from the engine."""

import json
import time

import pytest

from mulebox.dashboard.metrics import jobs_memory, jobs_memory_for, mac_jobs_memory
from mulebox.worker import darwin_jobs, docker_stats
from mulebox.worker.job_meter import SAMPLE_S, JobMeter, for_job

PS = """    1     1  12:05.66  19088
  500   500   0:01.50   2048
  501   500   1:00.25   1024
  600   600   2-01:00:00  10
  bad line
"""


def test_cpu_time_reads_every_ps_form():
    assert darwin_jobs.cpu_time("0:00.54") == 0.54
    assert darwin_jobs.cpu_time("135:39.25") == 135 * 60 + 39.25
    assert darwin_jobs.cpu_time("01:02:03") == 3723
    assert darwin_jobs.cpu_time("2-01:00:00") == 2 * 86400 + 3600


def test_parse_ps_and_group_memory():
    table = darwin_jobs.parse_ps(PS)
    assert table[1] == (500, 500, 1.5, 2048 * 1024)
    assert len(table) == 4
    assert darwin_jobs.group_memory({500}, table) == (2048 + 1024) * 1024


def test_the_engine_numbers_match_what_cgroups_give():
    stats = {"cpu_stats": {"cpu_usage": {"total_usage": 2_500_000_000}},
             "memory_stats": {"usage": 1000, "stats": {"inactive_file": 400}},
             "networks": {"eth0": {"rx_bytes": 10, "tx_bytes": 5}}}
    assert docker_stats.parse(stats) == {"cpu_s": 2.5, "memory": 600.0, "net": 15.0}
    assert docker_stats.parse({"memory_stats": {}}) is None
    assert docker_stats.Engine(path=None).stats("not/an id") is None


class FakeEngine:
    def __init__(self, numbers):
        self.numbers = numbers

    def stats(self, container):
        return self.numbers.get(container)


def settle(polled):
    """Let a background.Polled finish its first answer."""
    polled.value()
    end = time.monotonic() + 5
    while polled._task is not None and not polled._task.done:
        assert time.monotonic() < end
        time.sleep(0.01)


def test_the_reader_keys_each_process_so_new_ones_count_from_nothing():
    reader = darwin_jobs.JobReader(lambda: 500, None, lambda: darwin_jobs.parse_ps(PS))
    assert reader() == {"unit:500": 1.5, "unit:501": 60.25}
    meter = JobMeter(reader)
    meter.update(0.0)
    meter.update(SAMPLE_S)
    assert meter.cpu_pct == 0.0  # nothing grew between two equal readings


def test_unknown_is_never_idle():
    """No group yet, a group with no process, or containers not read: no reading at all."""
    table = lambda: darwin_jobs.parse_ps(PS)  # noqa: E731
    assert darwin_jobs.JobReader(lambda: None, None, table)() is None
    assert darwin_jobs.JobReader(lambda: 999, None, table)() is None
    assert darwin_jobs.JobReader(lambda: 500, None, lambda: None)() is None
    unread = darwin_jobs.ContainerStats(lambda: ["c1"], FakeEngine({}))
    settle(unread)
    assert darwin_jobs.JobReader(lambda: 500, unread, table)() is None


def test_containers_add_their_cpu_and_traffic():
    stats = darwin_jobs.ContainerStats(lambda: ["c1"], FakeEngine({"c1": {"cpu_s": 4.0, "net": 9.0}}))
    settle(stats)
    got = darwin_jobs.JobReader(lambda: 500, stats, lambda: darwin_jobs.parse_ps(PS))()
    assert got["service:c1"] == 4.0 and got["net:c1"] == 9.0


def test_for_job_uses_the_executors_groups_when_it_has_them():
    class MacExecutor:
        def pgid_of(self, name):
            return 500 if name == "mulebox-job-job-a" else None

    meter = for_job("job-a", False, docker=None, executor=MacExecutor())
    assert isinstance(meter._read, darwin_jobs.JobReader)
    assert not isinstance(for_job("job-a", False, docker=None)._read, darwin_jobs.JobReader)


def test_jobs_memory_on_a_mac_sums_recorded_groups_and_containers(tmp_path):
    records = tmp_path / "job-groups"
    records.mkdir()
    (records / "mulebox-job-job-a").write_text(json.dumps({"pgid": 500, "started": "x"}))
    (records / "mulebox-job-broken").write_text("not json")
    (records / "other").write_text(json.dumps({"pgid": 1}))
    table = lambda: darwin_jobs.parse_ps(PS)  # noqa: E731
    got = mac_jobs_memory(["c1"], [], records, table, FakeEngine({"c1": {"cpu_s": 0, "memory": 4096}}))
    assert got == (2048 + 1024) * 1024 + 4096
    assert mac_jobs_memory(["c2"], [], records, table, FakeEngine({})) is None
    assert mac_jobs_memory([], [], records, lambda: None) is None


@pytest.mark.parametrize("platform, mac", [("darwin", True), ("linux", False)])
def test_the_dashboard_picks_the_reader_for_its_system(monkeypatch, tmp_path, platform, mac):
    monkeypatch.setattr("mulebox.dashboard.metrics.sys.platform", platform)
    chosen = jobs_memory_for({"staging": str(tmp_path)})
    assert (chosen is not jobs_memory) == mac
