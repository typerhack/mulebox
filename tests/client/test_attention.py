"""Check-ins and unattended warnings as an agent reads them, end to end where it matters."""

import io
import json
import threading
import time

import pytest

from mulebox import cli
from mulebox.client import attention, events, queue_view, report
from mulebox.client.submit import Streams, Watcher
from mulebox.common.protocol import Message, MessageType
from mulebox.common.status import STOP_IDLE, job_event, shown_state, row
from mulebox.coordinator import leases

from .test_detached import FakeWorker, detach

JOB = "job-01JC3X0000000000000000ABCD"
VIEW = {"since": 10.0, "stop_reason": STOP_IDLE, "reason": "no activity while nobody watched",
        "stop_at": 910.0, "left_s": 750.0}
CHECK_IN = {"number": 2, "elapsed_s": 3600.0, "stage": "command", "output_idle_s": 95.0,
            "idle_s": 2.0, "cpu_pct": 180.0, "net_kib_s": 0.5}
STOPPED = {"job_id": JOB, "outcome": "cancelled", "exit_code": None, "duration_s": 1800.0,
           "stop_reason": STOP_IDLE}


def status_msg(**body):
    return Message(MessageType.STATUS_OK, "r", {"job_id": JOB, "state": "running", **body})


def test_a_stopped_job_has_its_own_exit_code_and_result():
    assert report.exit_code_for(STOPPED) == report.EXIT_STOPPED == 76
    assert shown_state(STOPPED) == "stopped: unattended"
    line = report.outcome_line(JOB, STOPPED)
    assert "stopped: unattended" in line and "no activity" in line and "not a failed" in line


def test_a_stop_the_job_beat_is_not_a_stop():
    done = {**STOPPED, "state": "finished", "outcome": "passed", "exit_code": 0}
    assert report.exit_code_for(done) == 0 and shown_state(done) == "passed"


def test_events_say_stopped_in_the_finished_line():
    event = job_event({**STOPPED, "state": "finished"})
    assert event["outcome"] == "stopped" and event["stop_reason"] == STOP_IDLE


def test_status_json_says_stopped_too():
    assert row({**STOPPED, "state": "finished"}, 0.0)["outcome"] == "stopped"


def test_124_keeps_its_meaning():
    assert report.exit_code_for({"outcome": "timed_out", "exit_code": 143}) == 124


def test_notices_are_events_with_their_keys():
    check_in = job_event({"job_id": JOB, "state": "running", "check_in": CHECK_IN})
    assert check_in["event"] == "check_in" and check_in["output_idle_s"] == 95.0
    assert check_in["v"] == 1 and check_in["job_id"] == JOB
    gone = job_event({"job_id": JOB, "state": "queued", "unattended": VIEW})
    assert gone["event"] == "unattended" and gone["left_s"] == 750.0


def test_a_check_in_line_gives_what_a_decision_needs():
    line = attention.check_in_line(JOB, CHECK_IN)
    for part in ("1h 00m", "stage command", "1m 35s ago", "180%", "0.5 KiB/s",
                 f"mulebox cancel {JOB}"):
        assert part in line


def test_a_reading_that_is_missing_is_left_out():
    line = attention.check_in_line(JOB, {"elapsed_s": 60.0, "output_idle_s": None})
    assert "None" not in line and "CPU" not in line


def test_the_warning_names_both_ways_out():
    line = attention.unattended_line(JOB, VIEW, {"project": "example-app", "job": "check"})
    assert "12m 30s" in line and f"mulebox wait {JOB}" in line
    assert f"mulebox cancel {JOB}" in line and "example-app check" in line


def test_watcher_prints_each_notice_once_and_keeps_the_log_clean():
    out, err = io.StringIO(), io.StringIO()
    watcher = Watcher(None, Streams(out=out, err=err))
    watcher.job_id = JOB
    message_with = status_msg(check_in=CHECK_IN)
    assert watcher.handle(message_with) is False
    watcher.handle(message_with)  # a reconnect sends the latest again
    watcher.handle(status_msg(check_in={**CHECK_IN, "number": 3}))
    assert err.getvalue().count("check-in") == 2 and out.getvalue() == ""


def test_events_lines_for_notices_stay_one_each_and_state_is_not_repeated():
    out = io.StringIO()
    stream = events.EventStream(None, Streams(out=out, err=io.StringIO()), events.as_json)
    stream.job_id = JOB
    started = status_msg(worker="build-1")
    for msg in (started, status_msg(check_in=CHECK_IN), started, status_msg(check_in=CHECK_IN)):
        stream.handle(msg)
    kinds = [json.loads(line)["event"] for line in out.getvalue().splitlines()]
    assert kinds == ["started", "check_in"]


@pytest.mark.parametrize("notice", [{"check_in": CHECK_IN}, {"unattended": VIEW}])
def test_a_final_result_is_always_a_finished_event(notice):
    out = io.StringIO()
    stream = events.EventStream(None, Streams(out=out, err=io.StringIO()), events.as_json)
    stream.job_id = JOB
    assert stream.handle(status_msg(**notice)) is False
    final = Message(MessageType.RESULT, "r", {**STOPPED, "state": "finished", **notice})
    assert stream.handle(final) is True
    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert lines[-1]["event"] == "finished" and lines[-1]["exit_code"] == 76


def test_the_queue_shows_the_mark_a_line_and_a_top_line():
    jobs = [{"job_id": JOB, "project": "example-app", "job": "check", "state": "running",
             "started_at": 0.0, "created_at": 0.0, "unattended": VIEW}]
    lines = queue_view.render_table(jobs, 100.0, full_ids=True)
    assert lines[0].startswith("! 1 unattended")
    assert any("! running" in line for line in lines)
    assert any("! unattended, 12m 30s left" in line and f"mulebox wait {JOB}" in line
               for line in lines)


def test_nothing_unattended_means_no_top_line():
    jobs = [{"job_id": JOB, "state": "running", "created_at": 0.0}]
    assert queue_view.render_table(jobs, 100.0)[0].startswith("ID")


def test_status_text_lines():
    lines = attention.status_lines({"job_id": JOB, "attended": False, "unattended": VIEW,
                                    "activity": CHECK_IN})
    assert any("activity: running 1h 00m" in line for line in lines)
    assert any("watched: no, unattended" in line for line in lines)
    assert attention.status_lines({"job_id": JOB}) == []  # an older coordinator


# End to end: the real client and the real coordinator code (conftest.py, `local`).

def later(store, staging, seconds):
    now = time.time() + seconds
    with store.write() as conn:
        conn.execute("UPDATE jobs SET worker_lease_until = ?", (now + 300.0,))
    return leases.expire(store, now, staging)


def test_a_job_left_alone_warns_from_any_command_and_json_stays_clean(local, in_project, capsys):
    store, staging = local.store, local.staging
    job_id, _ = detach(capsys)
    with store.write() as conn:
        conn.execute("UPDATE jobs SET client_lease_until = ?", (time.time() - 1,))
    assert cli.main(["status", job_id, "--json"]) == 0
    seen = capsys.readouterr()
    body = json.loads(seen.out)
    assert body["attended"] is False and body["unattended"]["left_s"] > 0
    assert f"job {job_id}" in seen.err and f"mulebox wait {job_id}" in seen.err


def test_a_stopped_queued_job_exits_76_through_wait(local, in_project, capsys):
    store, staging = local.store, local.staging
    job_id, _ = detach(capsys)
    assert later(store, staging, leases.CLIENT_LEASE_S + 90000.0) == [job_id]
    assert cli.main(["wait", job_id]) == 76
    assert "stopped: unattended" in capsys.readouterr().err


def test_wait_takes_a_job_back(local, in_project, capsys):
    store, staging = local.store, local.staging
    job_id, _ = detach(capsys)
    with store.write() as conn:
        conn.execute("UPDATE jobs SET client_lease_until = ?", (time.time() - 60,))
    worker = FakeWorker(store, staging, pause=1.0)
    thread = threading.Thread(target=worker.run_next)
    thread.start()
    code = cli.main(["wait", job_id])
    thread.join()
    assert code == 3
    assert "being watched again" in capsys.readouterr().err
