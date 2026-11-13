"""An agent job's download, from its log as the worker reads it, in its heartbeat's activity."""

from mulebox.common.status import INSTALL, IMAGES
from mulebox.worker import activity
from mulebox.worker.activity import SAMPLE_S, MachineMeter
from mulebox.worker.job_meter import JobMeter
from mulebox.worker.link import request
from mulebox.worker.logtail import LogTailer

T0 = 1_000_000.0


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


def tailer(tmp_path, clock):
    tail = LogTailer(tmp_path / "out.log", "job-1", "att-1", request, clock=clock)
    return tail


def write(tmp_path, tail, text):
    with open(tmp_path / "out.log", "a", encoding="utf-8") as fh:
        fh.write(text)
    tail.read_new()


def idle_job():
    readings = iter([{"unit": 0.0}, {"unit": 0.1}])
    job = JobMeter(lambda: next(readings))
    job.update(T0)
    job.update(T0 + SAMPLE_S)
    return job


def machine(kib_s):
    counters = iter([(0.0, 0), (1.0, int(kib_s * 1024 * SAMPLE_S))])
    meter = MachineMeter(lambda: next(counters))
    meter.update(T0)
    meter.update(T0 + SAMPLE_S)
    return meter


def test_a_pnpm_download_in_install_reaches_the_heartbeat_with_the_machines_traffic(tmp_path):
    clock = Clock()
    tail = tailer(tmp_path, clock)
    tail.steps.begin(INSTALL, T0)
    write(tmp_path, tail, "Downloading next@16.4.3: 48.31 kB/43.60 MB\n")
    clock.now = T0 + 20
    write(tmp_path, tail, "Downloading next@16.4.3: 12.05 MB/43.60 MB\n")
    got = activity.report(machine(600.0), idle_job(), T0, T0 + 20, INSTALL, None, T0 + 25,
                          tail.download)
    found = got["download"]
    assert (found["what"], found["name"], found["step"]) == ("package", "next@16.4.3", "install")
    assert (found["done_bytes"], found["total_bytes"]) == (12_050_000, 43_600_000)
    assert found["rate_bytes_s"] == round((12_050_000 - 48_310) / 20, 1)
    assert found["net_scope"] == "machine" and found["net_bytes_s"] == 600.0 * 1024
    assert found["waiting_on_network"] is True and found["stalled"] is False


def test_image_layers_count_as_the_pull_goes_and_a_new_stage_forgets_them(tmp_path):
    clock = Clock()
    tail = tailer(tmp_path, clock)
    tail.steps.begin(IMAGES, T0)
    write(tmp_path, tail, " 9986a736f7d3 Pulling fs layer 0B\n 9986a736f7d3 Downloading 2.097MB\n")
    clock.now = T0 + 10
    write(tmp_path, tail, " 9986a736f7d3 Downloading 22.5MB\n")
    found = activity.download(tail.download, MachineMeter(lambda: None), JobMeter(), IMAGES,
                              T0 + 12)
    assert (found["what"], found["done_bytes"], found["total_bytes"]) == ("image", 22_500_000, None)
    assert found["net_bytes_s"] is None and found["waiting_on_network"] is None
    tail.steps.begin(INSTALL, T0 + 13)
    assert activity.download(tail.download, MachineMeter(lambda: None), JobMeter(), INSTALL,
                             T0 + 14) is None


def test_a_compose_2_pull_gives_its_total(tmp_path):
    clock = Clock()
    tail = tailer(tmp_path, clock)
    tail.steps.begin(IMAGES, T0)
    write(tmp_path, tail, "a1b2c3d4e5f6 Downloading [==>    ]  12.3MB/45.6MB\n")
    found = tail.download.reading(T0 + 1)
    assert (found["done_bytes"], found["total_bytes"]) == (12_300_000, 45_600_000)


def test_nothing_downloading_is_null(tmp_path):
    tail = tailer(tmp_path, Clock())
    write(tmp_path, tail, "........ [ 40%]\n")
    got = activity.report(MachineMeter(lambda: None), JobMeter(), T0, T0, INSTALL, None, T0 + 1,
                          tail.download)
    assert got["download"] is None
