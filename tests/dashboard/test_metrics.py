from collections import namedtuple

from mulebox.dashboard import docker
from mulebox.dashboard.metrics import (
    Sampler, cpu_percent, disk_usage, parse_cpu, parse_memory,
)

STAT = "cpu  9 0 9 9 0 0 0 0\ncpu0 10 0 10 70 10 0 0 0 0 0\ncpu1 0 0 0 100 0 0 0 0\nintr 5\n"
MEMINFO = "MemTotal: 1000 kB\nMemFree: 100 kB\nMemAvailable: 400 kB\n"


def test_parse_cpu_counts_iowait_as_idle_and_skips_the_total_line():
    assert parse_cpu(STAT) == [(20, 100), (0, 100)]


def test_cpu_percent_between_samples():
    assert cpu_percent([(0, 100)], [(25, 200)]) == [25.0]
    assert cpu_percent([(0, 100)], [(0, 100)]) == [0.0]


def test_cpu_percent_needs_a_matching_previous_sample():
    assert cpu_percent([], [(1, 2)]) is None
    assert cpu_percent([(1, 2)], [(1, 2), (1, 2)]) is None


def test_parse_memory():
    assert parse_memory(MEMINFO) == {"total": 1024000, "available": 409600, "used": 614400}
    assert parse_memory("MemTotal: 1 kB\n") is None


def test_sampler_on_fixed_proc_files(tmp_path):
    (tmp_path / "stat").write_text(STAT)
    (tmp_path / "meminfo").write_text(MEMINFO)
    sampler = Sampler(tmp_path, wall=iter([0.0, 2.0]).__next__,
                      cpu_time=iter([0.0, 0.1]).__next__)
    sample = sampler.fast()
    assert sample["cpu"] is None  # the first sample has nothing to compare with
    assert sample["memory"]["used"] == 614400
    assert sample["self"]["cpu"] == 5.0
    assert sampler.cpu() == [0.0, 0.0]


def test_no_proc_is_not_an_error(tmp_path):
    sampler = Sampler(tmp_path)
    assert sampler.cpu() is None and sampler.memory() is None


def test_disk_usage_lists_a_file_system_once_and_skips_missing_roots(tmp_path):
    usage = namedtuple("usage", "total used free")(100, 40, 60)
    roots = {"jobs": str(tmp_path), "cache": str(tmp_path), "gone": str(tmp_path / "no")}
    assert disk_usage(roots, lambda path: usage) == [
        {"roots": ["cache", "jobs"], "total": 100, "used": 40, "free": 60}]


def test_docker_socket_choice():
    assert docker.socket_path({}) == docker.DEFAULT_SOCKET
    assert docker.socket_path({"DOCKER_HOST": "unix:///run/x.sock"}) == "/run/x.sock"
    assert docker.socket_path({"DOCKER_HOST": "tcp://192.168.1.50:2375"}) is None
