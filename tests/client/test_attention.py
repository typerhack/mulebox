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
from mulebox.common.status import STOP_STUCK, job_event, shown_state, row
from mulebox.coordinator import leases

from .test_detached import FakeWorker, detach

JOB = "job-01JC3X0000000000000000ABCD"
VIEW = {"since": 10.0, "stop_reason": STOP_STUCK, "reason": "no activity and no answer from the agent",
        "stop_at": 910.0, "left_s": 750.0}
CHECK_IN = {"number": 2, "elapsed_s": 3600.0, "stage": "command", "output_idle_s": 95.0,
            "idle_s": 2.0, "cpu_pct": 180.0, "net_kib_s": 0.5}
STOPPED = {"job_id": JOB, "outcome": "cancelled", "exit_code": None, "duration_s": 1800.0,
           "stop_reason": STOP_STUCK}


def status_msg(**body):
    return Message(MessageType.STATUS_OK, "r", {"job_id": JOB, "state": "running", **body})


def test_a_stopped_job_has_its_own_exit_code_and_result():
    assert report.exit_code_for(STOPPED) == report.EXIT_STOPPED == 76
    assert shown_state(STOPPED) == "stopped: stuck"
    line = report.outcome_line(JOB, STOPPED)
    assert "stopped: stuck" in line and "no activity" in line and "not a failed" in line


def test_a_stop_the_job_beat_is_not_a_stop():
    done = {**STOPPED, "state": "finished", "outcome": "passed", "exit_code": 0}
    assert report.exit_code_for(done) == 0 and shown_state(done) == "passed"


def test_events_say_stopped_in_the_finished_line():
    event = job_event({**STOPPED, "state": "finished"})
    assert event["outcome"] == "stopped" and event["stop_reason"] == STOP_STUCK


def test_status_json_says_stopped_too():
    assert row({**STOPPED, "state": "finished"}, 0.0)["outcome"] == "stopped"


def test_124_keeps_its_meaning():
    assert report.exit_code_for({"outcome": "timed_out", "exit_code": 143}) == 124


def test_notices_are_events_with_their_keys():
    check_in = job_event({"job_id": JOB, "state": "running", "check_in": CHECK_IN})
    assert check_in["event"] == "check_in" and check_in["output_idle_s"] == 95.0
    assert check_in["v"] == 1 and check_in["job_id"] == JOB


def test_a_check_in_line_gives_what_a_decision_needs():
    line = attention.check_in_line(JOB, CHECK_IN)
    for part in ("1h 00m", "stage command", "1m 35s ago", "180%", "0.5 KiB/s",
                 f"mulebox cancel {JOB}"):
        assert part in line


def test_a_reading_that_is_missing_is_left_out():
    line = attention.check_in_line(JOB, {"elapsed_s": 60.0, "output_idle_s": None})
    assert "None" not in line and "CPU" not in line


def test_the_reminder_names_both_answers():
    line = attention.question_line(JOB, VIEW, {"project": "example-app", "job": "check"})
    assert "12m 30s" in line and f"mulebox ok {JOB}" in line
    assert f"mulebox cancel {JOB}" in line and "example-app check" in line


def test_a_check_in_asks_and_names_both_answers():
    line = attention.check_in_line(JOB, CHECK_IN)
    assert "Is everything OK?" in line and f"mulebox ok {JOB}" in line


def test_a_result_from_while_away_says_not_to_retest():
    line = attention.away_line({"job_id": JOB, "project": "example-app", "job": "check",
                                "outcome": "passed", "exit_code": 0,
                                "base_commit": "a1b2c3d4e5f6a7b8"})
    assert "while you were away" in line and "passed" in line
    assert "a1b2c3d4e5" in line and "No need to retest" in line


def test_a_repeat_says_what_it_found():
    job = {"job_id": JOB, "state": "finished", "outcome": "failed", "exit_code": 2}
    line = attention.already_line(job)
    assert "already tested" in line and "exit 2" in line and "--again" in line
    assert "already running" in attention.already_line({"job_id": JOB, "state": "running"})


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
             "started_at": 0.0, "created_at": 0.0, "question": VIEW}]
    lines = queue_view.render_table(jobs, 100.0, full_ids=True)
    assert lines[0].startswith("! 1 waiting for an answer")
    assert any("! running" in line for line in lines)
    assert any("needs an answer, 12m 30s" in line and f"mulebox ok {JOB}" in line
               for line in lines)


def test_no_question_means_no_top_line():
    jobs = [{"job_id": JOB, "state": "running", "created_at": 0.0}]
    assert queue_view.render_table(jobs, 100.0)[0].startswith("ID")


def test_status_text_lines():
    lines = attention.status_lines({"job_id": JOB, "question": VIEW, "activity": CHECK_IN})
    assert any("activity: running 1h 00m" in line for line in lines)
    assert any("is everything OK?" in line for line in lines)
    assert attention.status_lines({"job_id": JOB}) == []  # an older coordinator


# End to end: the real client and the real coordinator code (conftest.py, `local`).

def test_a_job_that_finished_away_is_told_by_the_next_command(local, in_project, capsys):
    job_id, _ = detach(capsys)
    FakeWorker(local.store, local.staging, exit_code=0).run_next()
    assert cli.main(["projects"]) == 0
    seen = capsys.readouterr().err
    assert f"job {job_id}" in seen and "while you were away" in seen and "on commit" in seen
    assert cli.main(["projects"]) == 0
    assert "while you were away" not in capsys.readouterr().err


def test_a_repeat_check_runs_nothing_and_keeps_the_exit_code(local, in_project, capsys):
    thread = threading.Thread(target=FakeWorker(local.store, local.staging).run_next)
    thread.start()
    assert cli.main(["check", "test"]) == 3
    thread.join()
    capsys.readouterr()
    assert cli.main(["check", "test"]) == 3
    err = capsys.readouterr().err
    assert "already tested" in err
    assert "submitted" not in err and "dashboard" not in err


def test_a_detached_repeat_still_prints_an_id_for_wait(local, in_project, capsys):
    job_id, _ = detach(capsys)
    FakeWorker(local.store, local.staging).run_next()
    capsys.readouterr()
    assert cli.main(["check", "test", "--detach"]) == 0
    assert capsys.readouterr().out.strip() == job_id
    assert cli.main(["wait", job_id]) == 3


def test_ok_answers_a_job_question(local, in_project, capsys):
    job_id, _ = detach(capsys)
    assert cli.main(["ok", job_id]) == 0
    assert job_id in capsys.readouterr().out


def test_a_check_in_names_the_last_line():
    line = attention.check_in_line("job-1", {"elapsed_s": 60, "last_line": "tests: 40 of 90"})
    assert "last line: tests: 40 of 90" in line
