from collections import namedtuple

from mulebox.dashboard import docker
from mulebox.dashboard.metrics import (
    Sampler, cpu_percent, disk_usage, jobs_memory, parse_cpu, parse_memory, parse_swap,
)

STAT = "cpu  9 0 9 9 0 0 0 0\ncpu0 10 0 10 70 10 0 0 0 0 0\ncpu1 0 0 0 100 0 0 0 0\nintr 5\n"
MEMINFO = ("MemTotal: 1000 kB\nMemFree: 100 kB\nMemAvailable: 400 kB\n"
           "SwapTotal: 800 kB\nSwapFree: 600 kB\n")


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
    assert sample["swap"] == {"total": 819200, "used": 204800}
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
    assert docker.socket_path({}, default=__file__, context=lambda: None) == __file__
    assert docker.socket_path({"DOCKER_HOST": "unix:///run/x.sock"}) == "/run/x.sock"
    assert docker.socket_path({"DOCKER_HOST": "tcp://192.168.1.50:2375"}) is None


def test_the_fullest_disk_is_the_one_with_least_free(tmp_path):
    from mulebox.common import disk
    (tmp_path / "a").mkdir()
    sizes = {str(tmp_path): (100, 90, 10), str(tmp_path / "a"): (100, 20, 80)}
    usage = lambda path: namedtuple("usage", "total used free")(*sizes[path])  # noqa: E731
    assert disk.fullest({"jobs": str(tmp_path)}, usage) == {
        "roots": ["jobs"], "total": 100, "used": 90, "free": 10}
    assert disk.fullest({"gone": str(tmp_path / "no")}, usage) is None


def test_parse_swap():
    assert parse_swap(MEMINFO) == {"total": 819200, "used": 204800}
    assert parse_swap("SwapTotal: 0 kB\nSwapFree: 0 kB\n") == {"total": 0, "used": 0}
    assert parse_swap("MemTotal: 1 kB\n") is None


def _group(path, memory):
    path.mkdir(parents=True)
    (path / "memory.current").write_text(f"{memory}\n")


def test_jobs_memory_adds_job_units_busy_runners_and_containers(tmp_path):
    (tmp_path / "cgroup.controllers").write_text("cpu memory\n")
    uid = __import__("os").getuid()
    apps = tmp_path / f"user.slice/user-{uid}.slice/user@{uid}.service/app.slice"
    _group(apps / "mulebox-job-job-01.service", 100)
    _group(apps / "other.service", 999)
    _group(apps / "app-mulebox\\x2drunner.slice" / "mulebox-runner@busy.service", 20)
    _group(apps / "app-mulebox\\x2drunner.slice" / "mulebox-runner@idle.service", 999)
    _group(tmp_path / "system.slice/docker-c1.scope", 3)
    assert jobs_memory(["c1", "gone"], ["busy", "missing"], tmp_path) == 123


def test_job_memory_leaves_out_page_cache_it_can_drop(tmp_path):
    from mulebox.worker import cgroups
    _group(tmp_path / "g", 1000)
    (tmp_path / "g" / "memory.stat").write_text("anon 600\nfile 400\ninactive_file 300\n")
    assert cgroups.memory_bytes(tmp_path / "g") == 700
    (tmp_path / "g" / "memory.stat").unlink()
    assert cgroups.memory_bytes(tmp_path / "g") == 1000


def test_jobs_memory_without_cgroups_is_unknown(tmp_path):
    assert jobs_memory([], [], tmp_path) is None


def test_job_containers_by_label_and_by_runner_work_folder():
    root = "/home/alice/.mulebox/runners"
    listing = [{"Id": "a", "Labels": {"mulebox.job": "job-1"}},
               {"Id": "b", "Labels": {"com.docker.compose.project.working_dir":
                                      f"{root}/build-1-app/_work/app/app"}},
               {"Id": "c", "Labels": {"com.docker.compose.project.working_dir": "/srv/db"}},
               {"Id": "d", "Labels": None}, {"Labels": {}}]
    assert docker.job_containers(listing, root) == ["a", "b"]
    assert docker.job_containers(listing, None) == ["a"]


def test_docker_df_total_matches_docker_system_df():
    body = {"LayersSize": 1000, "Containers": [{"SizeRw": 5}, {}],
            "Volumes": [{"UsageData": {"Size": 7}}, {"UsageData": {"Size": -1}}, {}],
            "BuildCache": [{"Size": 30, "Shared": True}, {"Size": 2}]}
    assert docker.df_total(body) == 1044
    assert docker.df_total({"Images": []}) is None and docker.df_total(None) is None


def test_a_sampler_with_no_proc_reads_this_machine():
    from mulebox.common.host import DarwinHost, LinuxHost

    assert isinstance(Sampler().host, (DarwinHost, LinuxHost))  # not a service manager
