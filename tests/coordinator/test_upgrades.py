"""Upgrades that wait their turn in the queue (coordinator/upgrades.py, M16.5)."""

import pytest

from mulebox.common.protocol import JobState, Outcome
from mulebox.coordinator import api, leases, queue, reservations
from mulebox.coordinator import store as st
from mulebox.coordinator.errors import Conflict

from .helpers import claimed, queued, request


def ask(store, staging, now=1000.0, **body):
    reply = api.handle(store, staging, request("upgrade", **body), now)
    if reply.type == "error":
        raise Conflict(reply.body["message"])
    return reply.body


def line_up(store, staging, worker="wrk-a", now=1000.0, **extra):
    return ask(store, staging, now, action="queue", worker=worker, version="9.9.9", **extra)


def claim(store, worker="wrk-a", now=1001.0):
    return queue.claim(store, worker, ["node", "docker"], 2, 10, now=now)


def end(store, job_id, now=1002.0):
    with store.write() as conn:
        st.finish(conn, st.require_job(conn, job_id), Outcome.PASSED, now)


def test_first_in_line_nothing_new_starts_until_it_is_done(store, staging):
    running = claimed(store, staging, now=1.0)["job_id"]
    waiting = queued(store, staging, now=2.0)
    upgrade = line_up(store, staging, now=3.0)
    assert upgrade["position"] == 1 and upgrade["state"] == "queued"
    assert claim(store) is None  # this machine waits for the upgrade
    assert ask(store, staging, action="turn", job_id=upgrade["job_id"])["go"] is False
    end(store, running)
    assert claim(store) is None
    turn = ask(store, staging, action="turn", job_id=upgrade["job_id"])
    assert turn["go"] is True and turn["state"] == "running"
    assert claim(store) is None  # installing: still nothing new
    done = ask(store, staging, action="done", job_id=upgrade["job_id"], passed=True, log="ok\n")
    assert done["outcome"] == "passed"
    assert claim(store)["job_id"] == waiting  # the line goes on
    assert staging.log_path(upgrade["job_id"]).read_text() == "ok\n"


def test_other_machines_go_on(store, staging):
    claimed(store, staging, now=1.0)
    waiting = queued(store, staging, now=2.0)
    line_up(store, staging, now=3.0)
    assert claim(store, "wrk-b")["job_id"] == waiting


def test_behind_lets_the_jobs_already_waiting_go_first(store, staging):
    waiting = queued(store, staging, now=1.0)
    upgrade = line_up(store, staging, now=2.0, first=False)
    later = queued(store, staging, now=3.0)
    assert ask(store, staging, action="turn", job_id=upgrade["job_id"])["go"] is False
    assert claim(store)["job_id"] == waiting
    assert claim(store) is None  # `later` is behind the upgrade
    end(store, waiting)
    assert ask(store, staging, action="turn", job_id=upgrade["job_id"])["go"] is True
    ask(store, staging, action="done", job_id=upgrade["job_id"], passed=False)
    assert claim(store)["job_id"] == later


def test_a_waiter_that_stops_asking_lets_the_machine_go(store, staging):
    upgrade = line_up(store, staging, now=1000.0)
    waiting = queued(store, staging, now=1001.0)
    assert claim(store, now=1002.0) is None
    leases.expire(store, 1000.0 + 120.0)
    with store.read() as conn:
        assert st.require_job(conn, upgrade["job_id"])["outcome"] == Outcome.INTERRUPTED
    assert claim(store, now=1121.0)["job_id"] == waiting


def test_one_upgrade_per_machine_at_a_time(store, staging):
    line_up(store, staging)
    with pytest.raises(Conflict, match="already in line"):
        line_up(store, staging)
    line_up(store, staging, worker="wrk-b")


def test_a_github_slot_waits_behind_it(store, staging):
    line_up(store, staging, now=1.0)
    with store.write() as conn:
        slot = reservations.create(conn, {
            "pinned_worker": "wrk-a", "project": "o__r", "job": "build", "runner": "r1",
            "idempotency_key": "gh-1"}, 2.0)
        assert reservations.try_grant(conn, slot, 3.0, 10)["state"] == JobState.QUEUED


def test_a_waiting_upgrade_is_cancelled_like_a_job(store, staging):
    upgrade = line_up(store, staging)
    waiting = queued(store, staging, now=1001.0)
    api.handle(store, staging, request("cancel", job_id=upgrade["job_id"]), 1002.0)
    assert claim(store, now=1003.0)["job_id"] == waiting
    turn = ask(store, staging, now=1004.0, action="turn", job_id=upgrade["job_id"])
    assert turn["go"] is False and turn["outcome"] == "cancelled"


def test_a_waiting_upgrade_moves_and_shows_in_status(store, staging):
    waiting = queued(store, staging, now=1.0)
    upgrade = line_up(store, staging, now=2.0)["job_id"]
    api.handle(store, staging, request("job_control", job_id=upgrade, action="last"), 3.0)
    status = api.handle(store, staging, request("status", job_id=upgrade), 4.0).body
    assert status["kind"] == "upgrade" and status["position"] == 2
    assert status["place_reason"] == f"moved by hand, just behind {waiting}"
    with store.read() as conn:
        assert st.require_job(conn, waiting)["pin_side"] is None  # only the upgrade is pinned
    assert claim(store, now=5.0)["job_id"] == waiting
    paused = api.handle(store, staging, request("job_control", job_id=upgrade, action="boost"), 6.0)
    assert paused.type == "error" and "only move" in paused.body["message"]


def test_an_installing_upgrade_is_not_cancelled(store, staging):
    upgrade = line_up(store, staging)["job_id"]
    assert ask(store, staging, action="turn", job_id=upgrade)["go"] is True
    reply = api.handle(store, staging, request("cancel", job_id=upgrade), 1001.0)
    assert reply.type == "error" and "installing" in reply.body["message"]


def test_a_job_behind_it_says_why_it_waits(store, staging):
    upgrade = line_up(store, staging, now=1.0)["job_id"]
    waiting = queued(store, staging, now=2.0)
    body = api.handle(store, staging, request("status", job_id=waiting), 3.0).body
    assert upgrade in body["waiting_for"] and "upgrade of wrk-a" in body["waiting_for"]
    own = api.handle(store, staging, request("status", job_id=upgrade), 3.0).body
    assert "installs once the jobs running on wrk-a end" in own["waiting_for"]
