"""The job_steps table: reports from workers, and how a client reads them."""

import io

import pytest

from mulebox.common import status
from mulebox.common.protocol import MessageType, decode
from mulebox.coordinator import steps
from mulebox.coordinator.watch import watch

from .helpers import claimed, queued, request
from .test_api import T0, call


def row(seq=0, stage="prepare", **extra):
    return {"seq": seq, "stage": stage, "started_at": 100.0, "finished_at": None,
            "exit_code": None, "bytes_downloaded": None, "failing_line": None, **extra}


def ids(claim):
    return {"job_id": claim["job_id"], "attempt_id": claim["attempt_id"]}


def report(store, staging, claim, *rows):
    return call(store, staging, "steps", steps=list(rows), **ids(claim))


def test_rows_arrive_and_status_shows_them(store, staging):
    claim = claimed(store, staging)
    assert report(store, staging, claim, row(), row(1, "setup")).body["state"] == "starting"
    body = call(store, staging, "status", job_id=claim["job_id"]).body
    assert [r["stage"] for r in body["steps"]] == ["prepare", "setup"]


def test_a_row_is_replaced_by_its_seq(store, staging):
    claim = claimed(store, staging)
    report(store, staging, claim, row())
    report(store, staging, claim, row(finished_at=120.0, exit_code=0, bytes_downloaded=512))
    report(store, staging, claim, row(finished_at=120.0, exit_code=0, bytes_downloaded=512))
    with store.read() as conn:
        rows = steps.for_job(conn, claim["job_id"])
    assert len(rows) == 1
    assert rows[0]["finished_at"] == 120.0 and rows[0]["bytes_downloaded"] == 512


def test_a_stale_attempt_cannot_report(store, staging):
    claim = claimed(store, staging)
    reply = call(store, staging, "steps", steps=[row()], job_id=claim["job_id"],
                 attempt_id="att-01JC3X0000000000000000000Z")
    assert reply.body["code"] == "conflict"


def test_a_report_after_the_result_is_kept(store, staging):
    claim = claimed(store, staging)
    call(store, staging, "result", now=T0 + 9, outcome="passed", exit_code=0, duration_s=1,
         **ids(claim))
    assert report(store, staging, claim, row()).body["state"] == "finished"


def test_bad_rows_are_refused(store, staging):
    claim = claimed(store, staging)
    for bad in (row(stage="nonsense"), row(seq=-1), row(started_at="soon"), "text",
                row(exit_code="1"), row(bytes_downloaded=-1)):
        assert report(store, staging, claim, bad).body["code"] == "bad_request"
    many = [row(seq) for seq in range(steps.MAX_ROWS + 1)]
    assert report(store, staging, claim, *many).body["code"] == "bad_request"


def test_a_long_failing_line_is_cut(store, staging):
    claim = claimed(store, staging)
    report(store, staging, claim, row(failing_line="x" * 9000))
    with store.read() as conn:
        rows = steps.for_job(conn, claim["job_id"])
    assert len(rows[0]["failing_line"]) == status.MAX_FAILING_LINE


def test_a_queued_job_has_an_empty_list(store, staging):
    job_id = queued(store, staging)
    assert call(store, staging, "status", job_id=job_id).body["steps"] == []


# The failed stage in replies


def finish(store, staging, claim, outcome, exit_code=1):
    call(store, staging, "result", job_id=claim["job_id"], attempt_id=claim["attempt_id"],
         outcome=outcome, exit_code=exit_code, duration_s=1.0)


def test_status_and_the_watch_stream_name_the_stage_that_failed(store, staging):
    claim = claimed(store, staging)
    report(store, staging, claim, row(seq=0, stage="prepare", finished_at=T0, exit_code=0),
           row(seq=1, stage="setup", finished_at=T0, exit_code=2, failing_line="boom"),
           row(seq=2, stage="cleanup", finished_at=T0, exit_code=0))
    finish(store, staging, claim, "failed", exit_code=2)
    assert call(store, staging, "status", job_id=claim["job_id"]).body["stage"] == "setup"
    out = io.BytesIO()
    watch(store, staging, request("watch", job_id=claim["job_id"], offset=0), io.BytesIO(), out)
    replies = [decode(line) for line in out.getvalue().splitlines()]
    assert [reply.body["stage"] for reply in replies if reply.type in (
        MessageType.STATUS_OK, MessageType.RESULT)] == ["setup", "setup"]


@pytest.mark.parametrize("outcome", ["passed", "cancelled"])
def test_a_job_that_did_not_fail_names_no_stage(store, staging, outcome):
    claim = claimed(store, staging)
    report(store, staging, claim, row(finished_at=T0, exit_code=143))
    finish(store, staging, claim, outcome)
    assert "stage" not in call(store, staging, "status", job_id=claim["job_id"]).body


def test_a_failed_job_with_no_rows_names_no_stage(store, staging):
    claim = claimed(store, staging)
    finish(store, staging, claim, "failed")
    assert "stage" not in call(store, staging, "status", job_id=claim["job_id"]).body


# The status model


def test_current_stage_only_of_an_active_job():
    open_row = [row(), row(1, "command")]
    assert status.current_stage({"state": "running"}, open_row) == "command"
    assert status.current_stage({"state": "finished"}, open_row) is None
    assert status.current_stage({"state": "running"}, [row(finished_at=2.0)]) is None
    assert status.current_stage({"state": "queued"}, []) is None


def test_step_duration():
    assert status.step_duration_s(row(finished_at=130.0)) == 30.0
    assert status.step_duration_s(row(), now=110.0) == 10.0
    assert status.step_duration_s(row()) is None
    assert status.step_duration_s({}) is None


def test_failed_step_is_the_first_that_failed():
    rows = [row(exit_code=0), row(1, "command", exit_code=2, failing_line="boom"),
            row(2, "cleanup", exit_code=0)]
    assert status.failed_step(rows)["stage"] == "command"
    assert status.failed_step([row(exit_code=0)]) is None
    assert status.failed_step([row()]) is None
