"""The verdict of a running job (common/stuck.py): judged on its evidence, not a timer."""

import pytest

from mulebox.common import stuck

JOB = {"kind": "job", "state": "running", "paused": 0, "cancel_requested": 0}
LIMIT = 120.0
NOW = 1000.0


def report(**fields):
    return {"at": NOW, "idle_s": 0.0, "compute_idle_s": 0.0, "io_kib_s": 0.0,
            "last_line": "Running migrations...", "download": None, **fields}


def look(job=JOB, stage="command", **fields):
    return stuck.verdict(job, report(**fields), stage, LIMIT, NOW)


def test_a_job_that_moves_is_working():
    assert look(idle_s=30.0, compute_idle_s=30.0)["verdict"] == "working"


def test_nothing_moving_past_the_limit_is_stuck_with_its_evidence():
    seen = look(idle_s=310.0, compute_idle_s=310.0)
    assert seen["verdict"] == "stuck" and seen["since"] == NOW - 310.0
    assert seen["text"] == ('Looks stuck: no output, no CPU and no data moving for 5m 10s in '
                            'stage command. Last line: "Running migrations...".')


def test_an_old_report_is_aged_to_now():
    seen = stuck.verdict(JOB, report(at=NOW - 30.0, idle_s=100.0), "command", LIMIT, NOW)
    assert seen["verdict"] == "stuck" and seen["quiet_s"] == 130.0


def test_a_mac_node_says_it_did_not_read_data():
    seen = look(idle_s=200.0, io_kib_s=None)
    assert "no output and no CPU for 3m 20s" in seen["text"]


def test_a_trickle_of_data_with_no_cpu_is_slow_not_stuck():
    seen = look(idle_s=5.0, compute_idle_s=200.0, io_kib_s=6.0)
    assert seen["verdict"] == "slow"
    assert seen["text"] == ("Only a trickle of data moves: its processes read and write "
                            "6.1 KB/s, with no output and almost no CPU for 3m 20s.")


def test_a_slow_download_from_the_log_is_slow():
    download = {"what": "tool", "name": "node-v22.tar.xz", "rate_bytes_s": 12_000.0,
                "done_bytes": 41e6, "total_bytes": 300e6, "waiting_on_network": True,
                "stalled": False}
    seen = look(idle_s=0.0, compute_idle_s=0.0, download=download)
    assert seen["text"] == "Downloading slowly: 12.0 KB/s, 41.0 MB of 300.0 MB of node-v22.tar.xz."


def test_a_fast_download_is_working():
    download = {"what": "package", "rate_bytes_s": 2e6, "waiting_on_network": True}
    assert look(download=download)["verdict"] == "working"


def test_a_stalled_download_with_nothing_else_moving_is_stuck():
    download = {"what": "browser", "name": "chromium", "stalled": True, "done_bytes": 5e6,
                "total_bytes": 90e6}
    seen = look(idle_s=200.0, download=download)
    assert seen["verdict"] == "stuck" and "its download (5.0 MB of 90.0 MB of chromium)" in seen["text"]


@pytest.mark.parametrize("line", ["Overwrite existing files? [y/N]", "Password:",
                                  "? Which package manager do you want to use",
                                  "Press any key to continue", "Do you want to continue?"])
def test_a_question_for_input_is_asking(line):
    seen = look(idle_s=150.0, last_line=line)
    assert seen["verdict"] == "asking" and "never get" in seen["text"]


@pytest.mark.parametrize("line", ["Retrying in 60 s (attempt 3 of 5)", "Waiting for mysql...",
                                  "backing off for 30s"])
def test_a_line_that_says_it_waits_is_waiting_until_it_waits_too_long(line):
    assert look(idle_s=200.0, last_line=line)["verdict"] == "waiting"
    late = look(idle_s=stuck.WAITING_FOR * LIMIT + 1, last_line=line)
    assert late["verdict"] == "stuck" and "it said it was waiting" in late["text"]


@pytest.mark.parametrize("job", [{**JOB, "state": "queued"}, {**JOB, "paused": 1},
                                 {**JOB, "cancel_requested": 1}, {**JOB, "kind": "runner"}])
def test_no_verdict_for_a_job_that_is_not_simply_running(job):
    assert look(job=job, idle_s=900.0) is None


def test_not_knowing_is_never_stuck():
    assert look(idle_s=None, compute_idle_s=None) is None
    assert stuck.verdict(JOB, {}, "command", LIMIT, NOW) is None


def test_data_under_twice_the_slow_line_is_slow_and_above_it_working():
    assert look(idle_s=5.0, compute_idle_s=200.0, io_kib_s=90.0)["verdict"] == "slow"
    assert look(idle_s=5.0, compute_idle_s=200.0, io_kib_s=120.0)["verdict"] == "working"
