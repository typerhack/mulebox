"""`job_control` requests: pause, resume, moves in line, boost and normal on one job (M14.3)."""

import pytest

from mulebox.common.protocol import JobState
from mulebox.coordinator import api, attendance, line, queue
from mulebox.coordinator import store as st
from mulebox.coordinator.errors import BadRequest, Conflict
from mulebox.coordinator.views import PAUSED_REASON

from .helpers import claimed, queued, request


def act(store, staging, job_id, action, now=1000.0):
    reply = api.handle(store, staging, request("job_control", job_id=job_id, action=action), now)
    if reply.type == "error":
        raise {"conflict": Conflict, "bad_request": BadRequest}.get(
            reply.body["code"], RuntimeError)(reply.body["message"])
    return reply.body


def job(store, job_id):
    with store.read() as conn:
        return st.require_job(conn, job_id)


def claim(store, worker="wrk-a", now=1001.0):
    return queue.claim(store, worker, ["node", "docker"], 2, 10, now=now)


def test_a_paused_waiting_job_keeps_its_place_and_does_not_start(store, staging):
    paused = queued(store, staging, now=1.0)
    later = queued(store, staging, now=2.0)
    body = act(store, staging, paused, "pause")
    assert body["paused"] is True and body["action"] == "pause"
    reply = api.handle(store, staging, request("status", job_id=paused), 3.0)
    assert reply.body["waiting_for"] == PAUSED_REASON and reply.body["position"] == 1
    assert claim(store)["job_id"] == later
    act(store, staging, paused, "resume")
    assert claim(store, "wrk-b")["job_id"] == paused


def test_first_goes_before_older_jobs(store, staging):
    older = queued(store, staging, now=1.0)
    newer = queued(store, staging, now=2.0)
    act(store, staging, newer, "first")
    first, second = job(store, newer), job(store, older)
    with store.read() as conn:
        assert queue.position(conn, first) == 1 and queue.position(conn, second) == 2
    assert claim(store)["job_id"] == newer


def test_first_twice_and_on_two_jobs_keeps_the_latest_ahead(store, staging):
    a, b = queued(store, staging, now=1.0), queued(store, staging, now=2.0)
    act(store, staging, a, "first")
    before = job(store, a)
    assert before["pin_side"] == "front" and before["priority"] == 0
    act(store, staging, a, "first")
    assert job(store, a) == before  # already leads: nothing changes
    act(store, staging, b, "first")
    assert _line(store) == [b, a]
    assert claim(store)["job_id"] == b


def test_a_boosted_job_gets_its_machine_to_itself(store, staging):
    running = claimed(store, staging, now=1.0)["job_id"]
    queued(store, staging, now=2.0)
    act(store, staging, running, "boost")
    assert claim(store, "wrk-a", now=3.0) is None  # its machine takes nothing new
    assert claim(store, "wrk-b", now=3.0) is not None  # others still do
    act(store, staging, running, "normal")
    queued(store, staging, now=4.0)
    assert claim(store, "wrk-a", now=5.0) is not None


def test_boosting_a_waiting_job_also_moves_it_first(store, staging):
    queued(store, staging, now=1.0)
    boosted = queued(store, staging, now=2.0)
    act(store, staging, boosted, "boost")
    assert claim(store)["job_id"] == boosted


def test_a_paused_running_job_is_not_asked_and_resuming_answers(store, staging):
    body = claimed(store, staging, now=1.0, timeout_min=1)
    job_id = body["job_id"]
    with store.write() as conn:
        st.transition(conn, st.require_job(conn, job_id), JobState.RUNNING)
        st.update_job(conn, job_id, active_at=1.0)
    limits = attendance.Limits()
    act(store, staging, job_id, "pause", now=10.0)
    assert attendance.question(job(store, job_id), 500.0, limits) is None
    reply = api.handle(store, staging, request("heartbeat", job_id=job_id, lease="worker",
                                               attempt_id=body["attempt_id"]), 20.0)
    assert reply.body["paused"] is True  # the worker freezes it from this
    act(store, staging, job_id, "resume", now=500.0)
    resumed = job(store, job_id)
    assert resumed["check_in_ok"] == 8 and resumed["active_at"] == 500.0
    assert attendance.question(resumed, 510.0, limits) is None


def test_what_cannot_be_steered(store, staging):
    job_id = queued(store, staging)
    with pytest.raises(BadRequest, match="action"):
        act(store, staging, job_id, "explode")
    api.handle(store, staging, request("cancel", job_id=job_id), 1001.0)
    with pytest.raises(Conflict, match="nothing to pause"):
        act(store, staging, job_id, "pause")
    running = claimed(store, staging, now=1002.0)["job_id"]
    with pytest.raises(Conflict, match="only a waiting job"):
        act(store, staging, running, "first")


def _line(store):
    with store.read() as conn:
        return [row["job_id"] for row in line.read(conn, 1000.0).rows]


def _four(store, staging):
    return [queued(store, staging, now=float(n)) for n in range(1, 5)]


def _pins(store, ids):
    with store.read() as conn:
        return {job_id: st.require_job(conn, job_id)["pin_side"] for job_id in ids}


def test_up_passes_the_job_ahead_and_pins_only_the_moved_one(store, staging):
    a, b, c, d = _four(store, staging)
    act(store, staging, c, "up")
    assert _line(store) == [a, c, b, d]
    assert _pins(store, [a, b, c, d]) == {a: None, b: None, c: "before", d: None}
    assert job(store, c)["pin_job"] == b
    later = queued(store, staging, now=9.0)
    assert _line(store) == [a, c, b, d, later]


def test_down_lets_the_job_behind_go_first(store, staging):
    a, b, c, d = _four(store, staging)
    act(store, staging, a, "down")
    assert _line(store) == [b, a, c, d]
    act(store, staging, a, "down")
    assert _line(store) == [b, c, a, d]
    assert _pins(store, [b, c, d]) == {b: None, c: None, d: None}
    assert claim(store)["job_id"] == b and claim(store, "wrk-b")["job_id"] == c
    assert _line(store) == [a, d]  # the jobs it was moved behind have started


def test_first_goes_to_the_front_and_stays_ahead_of_later_jobs(store, staging):
    a, b, c, d = _four(store, staging)
    act(store, staging, d, "first")
    later = queued(store, staging, now=9.0)
    assert _line(store) == [d, a, b, c, later]
    assert _pins(store, [a, b, c]) == {a: None, b: None, c: None}


def test_last_goes_to_the_end_ahead_of_jobs_sent_later(store, staging):
    a, b, c, d = _four(store, staging)
    act(store, staging, a, "last")
    assert _line(store) == [b, c, d, a]
    later = queued(store, staging, now=9.0)
    assert _line(store) == [b, c, d, a, later]
    for worker in ("wrk-a", "wrk-b", "wrk-c"):
        claim(store, worker)
    assert _line(store) == [a, later]  # the job it went behind started: it keeps that place


def test_up_down_first_and_last_reorder_the_line(store, staging):
    a, b, c, d = (queued(store, staging, now=float(n)) for n in range(1, 5))
    act(store, staging, c, "up")
    assert _line(store) == [a, c, b, d]
    act(store, staging, a, "down")
    assert _line(store) == [c, a, b, d]
    act(store, staging, c, "last")
    assert _line(store) == [a, b, d, c]
    act(store, staging, d, "first")
    assert _line(store) == [d, a, b, c]
    act(store, staging, d, "up")  # already first: nothing moves
    act(store, staging, c, "down")
    assert _line(store) == [d, a, b, c]
    later = queued(store, staging, now=9.0)
    assert _line(store)[-1] == later  # a job sent later still comes after the moved ones
    assert claim(store)["job_id"] == d


def test_normal_ends_a_boost_and_keeps_the_place(store, staging):
    older = queued(store, staging, now=1.0)
    newer = queued(store, staging, now=2.0)
    act(store, staging, newer, "boost")
    act(store, staging, newer, "normal")
    assert job(store, newer)["boost"] is False and _line(store) == [newer, older]


def test_only_a_job_in_line_moves(store, staging):
    running = claimed(store, staging, now=1.0)["job_id"]
    with pytest.raises(Conflict, match="moves in line"):
        act(store, staging, running, "down")
