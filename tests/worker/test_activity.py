"""The worker's reading of what a job is doing; nothing here is a real machine's /proc."""

from mulebox.common.status import COMMAND, IMAGES
from mulebox.worker import activity
from mulebox.worker.activity import MachineMeter, SAMPLE_S

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
    assert activity.net_bytes(NET) == 3000


def test_read_counters_from_a_proc_folder(tmp_path):
    (tmp_path / "net").mkdir()
    (tmp_path / "stat").write_text(STAT)
    (tmp_path / "net" / "dev").write_text(NET)
    assert activity.read_counters(tmp_path) == (2.0, 3000)


def test_no_proc_is_unknown(tmp_path):
    assert activity.read_counters(tmp_path) is None


def report(meter, now, output_at=0.0, stage=COMMAND):
    return meter.report(0.0, output_at, stage, now)


def test_unknown_until_the_first_span_is_measured():
    meter = MachineMeter(scripted((0.0, 0)))
    meter.update(0.0)
    assert report(meter, 1.0)["idle_s"] is None


def test_no_proc_stays_unknown():
    meter = MachineMeter(lambda: None)
    meter.update(0.0)
    meter.update(100.0)
    assert report(meter, 100.0)["idle_s"] is None


def test_a_failed_read_forgets_what_was_known():
    meter = MachineMeter(scripted((0.0, 0), (9.0, 0), None))
    meter.update(0.0)
    meter.update(SAMPLE_S)
    assert report(meter, SAMPLE_S)["idle_s"] == 0.0
    meter.update(SAMPLE_S * 2)
    assert report(meter, SAMPLE_S * 2)["idle_s"] is None


def test_a_quiet_machine_and_quiet_output_add_up_to_idle():
    meter = MachineMeter(scripted((0.0, 0), (0.1, 100), (0.2, 200)))
    for at in (0.0, SAMPLE_S, SAMPLE_S * 2):
        meter.update(at)
    got = report(meter, 70.0)
    assert got["idle_s"] == 70.0 and got["output_idle_s"] == 70.0


def test_cpu_alone_is_activity():
    meter = MachineMeter(scripted((0.0, 0), (30.0, 0)))
    meter.update(0.0)
    meter.update(SAMPLE_S)
    got = report(meter, SAMPLE_S + 2)
    assert got["idle_s"] == 2.0 and got["output_idle_s"] == SAMPLE_S + 2
    assert got["cpu_pct"] == 100.0


def test_network_alone_is_activity():
    meter = MachineMeter(scripted((0.0, 0), (0.0, 1024 * 1024)))
    meter.update(0.0)
    meter.update(SAMPLE_S)
    assert report(meter, SAMPLE_S)["idle_s"] == 0.0


def test_output_alone_is_activity():
    meter = MachineMeter(scripted((0.0, 0), (0.0, 0)))
    meter.update(0.0)
    meter.update(SAMPLE_S)
    assert report(meter, 40.0, output_at=39.0)["idle_s"] == 1.0


def test_an_idle_database_is_no_activity():
    """Below a tenth of a core, however long."""
    meter = MachineMeter(scripted((0.0, 0), (2.0, 0)))
    meter.update(0.0)
    meter.update(SAMPLE_S)
    assert report(meter, SAMPLE_S)["idle_s"] == SAMPLE_S


def test_image_builds_are_never_idle():
    meter = MachineMeter(scripted((0.0, 0), (0.0, 0)))
    meter.update(0.0)
    meter.update(SAMPLE_S)
    assert report(meter, 1000.0, stage=IMAGES)["idle_s"] is None


def test_samples_only_every_so_often():
    calls = []
    meter = MachineMeter(lambda: calls.append(1) or (0.0, 0))
    for at in (0.0, 1.0, 2.0, SAMPLE_S, SAMPLE_S + 1):
        meter.update(at)
    assert len(calls) == 2
