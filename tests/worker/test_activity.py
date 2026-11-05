"""The worker's reading of what a job is doing; nothing here is a real machine's /proc."""

from mulebox.common.status import COMMAND, IMAGES
from mulebox.worker import activity, cgroups
from mulebox.worker.activity import SAMPLE_S, MachineMeter
from mulebox.worker.job_meter import JobMeter

STAT = "cpu  90 0 10 800 100 0 0 0\ncpu0 40 0 10 400 50 0 0 0\ncpu1 50 0 0 400 50 0 0 0\nintr 1\n"
NET = ("Inter-|   Receive\n face |bytes packets errs drop fifo frame compressed multicast|"
       "bytes packets\n    lo: 500 1 0 0 0 0 0 0 500 1 0 0 0 0 0 0\n"
       "  eth0: 1000 1 0 0 0 0 0 0 2000 1 0 0 0 0 0 0\n")


def scripted(*counters):
    values = iter(counters)
    return lambda: next(values)


def test_busy_time_counts_waiting_on_a_disk():
    assert activity.busy_seconds(STAT) == (50 + 50 + 50 + 50) / 100


def test_network_leaves_out_loopback():
    assert cgroups.net_bytes(NET) == 3000


def test_read_counters_from_a_proc_folder(tmp_path):
    (tmp_path / "net").mkdir()
    (tmp_path / "stat").write_text(STAT)
    (tmp_path / "net" / "dev").write_text(NET)
    assert activity.read_counters(tmp_path) == (2.0, 3000)


def test_no_proc_is_unknown(tmp_path):
    assert activity.read_counters(tmp_path) is None


def report(job, now, output_at=0.0, stage=COMMAND):
    return activity.report(MachineMeter(lambda: None), job, 0.0, output_at, stage, now)


def job_with(*readings):
    job = JobMeter(scripted(*readings))
    for index in range(len(readings)):
        job.update(index * SAMPLE_S)
    return job


def test_machine_readings_are_kept_and_decide_nothing():
    machine = MachineMeter(scripted((0.0, 0), (30.0, 3 * 1024 * 1024)))
    machine.update(0.0)
    machine.update(SAMPLE_S)
    job = job_with({"unit": 0.0}, {"unit": 0.0})
    got = activity.report(machine, job, 0.0, 0.0, COMMAND, SAMPLE_S)
    assert got["cpu_pct"] == 100.0 and got["net_kib_s"] == 102.4
    assert got["idle_s"] == SAMPLE_S and got["job_cpu_pct"] == 0.0


def test_output_alone_is_activity():
    job = job_with({"unit": 0.0}, {"unit": 0.0})
    assert report(job, 40.0, output_at=39.0)["idle_s"] == 1.0


def test_unknown_is_never_idle():
    assert report(JobMeter(), 1000.0)["idle_s"] is None


def test_image_builds_are_never_idle():
    assert report(job_with({"unit": 0.0}, {"unit": 0.0}), 1000.0, stage=IMAGES)["idle_s"] is None


def test_samples_only_every_so_often():
    calls = []
    meter = MachineMeter(lambda: calls.append(1) or (0.0, 0))
    for at in (0.0, 1.0, 2.0, SAMPLE_S, SAMPLE_S + 1):
        meter.update(at)
    assert len(calls) == 2
