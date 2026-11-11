"""`mulebox events` and `status`: with the fake coordinator, then with the real coordinator."""

import json
import threading

import pytest

from mulebox import cli
from mulebox.client import events, submit
from mulebox.common.protocol import Message, MessageType
from mulebox.common.status import job_event

from .test_detached import FakeWorker, detach

JOB = "job-01JC3X0000000000000000ABCD"


def lines_of(text):
    return [json.loads(line) for line in text.splitlines()]


def test_each_state_maps_to_one_event():
    assert job_event({"job_id": JOB, "state": "queued", "position": 2})["position"] == 2
    assert job_event({"job_id": JOB, "state": "uploading"})["event"] == "queued"
    started = job_event({"job_id": JOB, "state": "running", "worker": "build-1"})
    assert started["event"] == "started" and started["machine"] == "build-1"
    finished = job_event({"job_id": JOB, "state": "finished", "outcome": "failed", "exit_code": 2})
    assert finished["event"] == "finished" and finished["outcome"] == "failed"


def test_starting_running_and_cleaning_are_one_event():
    shapes = [job_event({"job_id": JOB, "state": state, "worker": "build-1"})["event"]
              for state in ("starting", "running", "cleaning")]
    assert shapes == ["started"] * 3


def test_an_unknown_state_is_no_event():
    assert job_event({"job_id": JOB, "state": "something-new"}) is None


def test_the_format_is_versioned_and_says_what_it_is():
    event = job_event({"job_id": JOB, "state": "queued", "position": 1})
    assert {"v", "event", "job_id", "state"} <= set(event) and event["v"] == 1


def test_a_finished_event_carries_the_exit_code_of_the_command():
    msg = Message(MessageType.RESULT, "r", {"job_id": JOB, "outcome": "timed_out",
                                            "exit_code": None, "duration_s": 1.0})
    assert events.event_of(msg)["exit_code"] == 124


def test_events_have_no_log_text(fake, capsys):
    fake.scenario(log=["secret log line\n"], outcome="failed", exit_code=3)
    assert cli.main(["events", "--job", JOB, "--json"]) == 3
    out = capsys.readouterr().out
    assert "secret log line" not in out
    assert [e["event"] for e in lines_of(out)] == ["queued", "started", "finished"]


def test_every_line_is_json_with_the_facts(fake, capsys):
    fake.scenario(log=[], outcome="failed", exit_code=3)
    cli.main(["events", "--job", JOB, "--json"])
    queued, started, finished = lines_of(capsys.readouterr().out)
    assert queued["position"] == 2 and started["machine"] == "build-1"
    assert finished["outcome"] == "failed" and finished["exit_code"] == 3
    assert fake.requests()[0]["body"]["log"] is False
    assert fake.requests()[0]["body"]["lease"] is False


def test_a_dropped_connection_repeats_nothing_and_keeps_the_final_line(fake, capsys, monkeypatch):
    monkeypatch.setattr(submit, "WATCH_RETRY_DELAY_S", 0)
    fake.scenario(log=["only chunk\n"], drop_watch_once=True, outcome="failed", exit_code=7)
    assert cli.main(["events", "--job", JOB, "--json"]) == 7
    captured = capsys.readouterr()
    assert [e["event"] for e in lines_of(captured.out)] == ["queued", "started", "finished"]
    assert "reconnecting" in captured.err
    assert len([r for r in fake.requests() if r["type"] == "watch"]) == 2


def test_events_with_the_machine_down_exits_3(fake, capsys):
    fake.scenario(down=True)
    assert cli.main(["events", "--job", JOB, "--json"]) == 3
    assert "not affected" in capsys.readouterr().err


def test_text_lines_without_json(fake, capsys):
    fake.scenario(log=[], outcome="passed")
    assert cli.main(["events", "--job", JOB]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "queued, position 2", "started on build-1", "finished: passed, exit code 0"]


@pytest.mark.parametrize("state,expected", [
    ("queued", "queued"), ("running", "running"),
])
def test_status_prints_the_state(fake, capsys, state, expected):
    fake.scenario(status_state=state)
    assert cli.main(["status", JOB]) == 0
    assert expected in capsys.readouterr().out


def test_status_json_has_derived_fields(fake, capsys):
    fake.scenario(status_state="finished", outcome="failed", exit_code=2)
    assert cli.main(["status", JOB, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["state"] == "finished" and data["shown_state"] == "failed"
    assert data["exit_code"] == 2 and data["section"] == "recent"


def test_status_of_a_failed_job_still_exits_0(fake, capsys):
    fake.scenario(status_state="finished", outcome="failed", exit_code=2)
    assert cli.main(["status", JOB]) == 0
    assert "failed" in capsys.readouterr().out


def test_status_of_an_unknown_job_exits_4(fake, capsys):
    fake.scenario(error="not_found")
    assert cli.main(["status", JOB]) == 4


def test_events_follow_a_real_job_through_the_queue(local, in_project, capsys, monkeypatch):
    first, _ = detach(capsys)
    second, _ = detach(capsys)
    worker = FakeWorker(local.store, local.staging, pause=0.8)
    # The first job starts only once `events` has printed the second at #2: a fixed wait was
    # too short on a loaded node, and the #2 line was never seen.
    printed, handle = threading.Event(), events.EventStream.handle

    def noted(self, msg):
        try:
            return handle(self, msg)
        finally:
            printed.set()

    monkeypatch.setattr(events.EventStream, "handle", noted)

    def work():
        printed.wait(10)
        worker.run_next()
        worker.run_next()

    thread = threading.Thread(target=work)
    thread.start()
    code = cli.main(["events", "--job", second, "--json"])
    thread.join()
    out = capsys.readouterr().out
    lines = lines_of(out)
    assert code == 3 and "line one" not in out
    assert [e["event"] for e in lines] == ["queued", "queued", "started", "finished"]
    assert [lines[0]["position"], lines[1]["position"]] == [2, 1]
    assert lines[1]["running_ahead"] == [first]
    assert lines[2]["machine"] == "build-1"
    assert lines[3]["outcome"] == "failed" and lines[3]["exit_code"] == 3
    assert {e["job_id"] for e in lines} == {second} and first != second


def test_events_say_when_a_job_enters_a_stage(local, in_project, capsys):
    job_id, _ = detach(capsys)
    rows = tuple({"seq": seq, "stage": stage, "started_at": 1.0 + seq, "finished_at": None,
                  "exit_code": None} for seq, stage in enumerate(("prepare", "command")))
    worker = FakeWorker(local.store, local.staging, exit_code=0, pause=1.0, steps=rows)
    thread = threading.Thread(target=worker.run_next)
    thread.start()
    code = cli.main(["events", "--job", job_id, "--json"])
    thread.join()
    stages = [e for e in lines_of(capsys.readouterr().out) if e["event"] == "stage"]
    assert code == 0 and stages[-1]["stage"] == "command" and stages[-1]["number"] == 1


def test_queued_says_what_it_is_behind():
    line = events.as_text({"event": "queued", "position": 1, "running_ahead": ["job-1"]})
    assert line == "queued, position 1, behind job-1"


def test_stage_events_read_as_text():
    assert events.as_text({"event": "stage", "stage": "services"}) == "stage services"


def test_events_after_the_job_ended_still_give_the_result(local, in_project, capsys):
    job_id, _ = detach(capsys)
    FakeWorker(local.store, local.staging, exit_code=0).run_next()
    assert cli.main(["events", "--job", job_id, "--json"]) == 0
    lines = lines_of(capsys.readouterr().out)
    assert len(lines) == 1 and lines[0]["outcome"] == "passed"


def test_events_send_no_log_from_the_real_coordinator(local, in_project, capsys, monkeypatch):
    job_id, _ = detach(capsys)
    FakeWorker(local.store, local.staging).run_next()
    seen = []
    original = submit.Watcher.handle

    def spy(self, msg):
        seen.append(msg.type)
        return original(self, msg)

    monkeypatch.setattr(events.EventStream, "handle", spy, raising=False)
    monkeypatch.setattr(submit.Watcher, "write_log", lambda *_: None)
    cli.main(["events", "--job", job_id, "--json"])
    assert MessageType.LOG_CHUNK not in seen and MessageType.RESULT in seen


def test_status_of_a_real_job(local, in_project, capsys):
    job_id, _ = detach(capsys)
    assert cli.main(["status", job_id, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["position"] == 1 and data["project"] == "example-app" and data["job"] == "test"
    assert data["detached"] is True and data["section"] == "queued"
    FakeWorker(local.store, local.staging).run_next()
    assert cli.main(["status", job_id]) == 0
    assert "failed (exit 3)" in capsys.readouterr().out
