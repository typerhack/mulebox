"""A person's hold on a node (coordinator/node_hold.py), with the real coordinator code."""

from mulebox.common.protocol import MessageType
from mulebox.coordinator import leases, node_hold, queue
from mulebox.coordinator import store as st

from .helpers import queued
from .test_attendance import T0, call


def node(store, staging, now=T0, free=2, worker="wrk-a", **extra):
    return call(store, staging, "claim", now, worker=worker, capabilities=["node"],
                free_slots=free, **extra)


def hold(store, staging, now=T0, **body):
    return call(store, staging, "hold", now, action="make", node="wrk-a", **body)


def turn(store, staging, job_id, now):
    return call(store, staging, "hold", now, action="turn", job_id=job_id).body


def held(store, staging, now=T0 + 1, **body):
    made = hold(store, staging, now, **body).body
    said = turn(store, staging, made["job_id"], now)
    assert said["go"], said
    return made["job_id"]


def test_an_unknown_node_is_refused_with_its_code(store, staging):
    reply = hold(store, staging)
    assert reply.type is MessageType.ERROR and reply.body["error_code"] == "node.unknown"


def test_the_whole_node_held_starts_nothing_until_let_go(store, staging):
    node(store, staging)
    job_id = held(store, staging)
    queued(store, staging, T0 + 2)
    assert node(store, staging, T0 + 3).type is MessageType.CLAIM_NONE
    with store.read() as conn:
        assert queue.held_slots(conn, "wrk-a") == 2
    said = call(store, staging, "hold", T0 + 4, action="release", job_id=job_id).body
    assert (said["state"], said["ended"]) == ("finished", "let go")
    assert node(store, staging, T0 + 5).type is MessageType.CLAIM_OK


def test_some_slots_held_leave_the_rest_to_jobs(store, staging):
    node(store, staging)
    held(store, staging, slots=1)
    queued(store, staging, T0 + 2, branch="a")
    queued(store, staging, T0 + 3, branch="b")
    assert node(store, staging, T0 + 4, free=2).type is MessageType.CLAIM_OK
    assert node(store, staging, T0 + 5, free=1).type is MessageType.CLAIM_NONE


def test_it_waits_behind_jobs_already_in_line_and_says_why(store, staging):
    node(store, staging, free=0)  # busy: nothing claimed
    queued(store, staging, T0 + 1)
    made = hold(store, staging, T0 + 2).body
    assert made["position"] == 2 and "nothing ahead in line" in made["waiting_for"]
    assert not turn(store, staging, made["job_id"], T0 + 3)["go"]
    assert node(store, staging, T0 + 4, free=2).type is MessageType.CLAIM_OK  # the job first
    assert not turn(store, staging, made["job_id"], T0 + 5)["go"]  # the job holds a slot


def test_next_puts_it_first_and_jobs_behind_it_wait_naming_it(store, staging):
    node(store, staging, free=0)
    job = queued(store, staging, T0 + 1)
    made = hold(store, staging, T0 + 2, next=True).body
    assert made["position"] == 1
    assert node(store, staging, T0 + 3, free=2).type is MessageType.CLAIM_NONE
    why = call(store, staging, "status", T0 + 3, job_id=job).body["waiting_for"]
    assert why.startswith(f"a hold of wrk-a is ahead of it in line ({made['job_id']})")
    assert turn(store, staging, made["job_id"], T0 + 4)["go"]
    why = call(store, staging, "status", T0 + 5, job_id=job).body["waiting_for"]
    assert why.startswith("wrk-a is held (the whole node) by hold until")


def test_a_quiet_dev_machine_ends_a_waiting_hold(store, staging):
    node(store, staging, free=0)
    queued(store, staging, T0 + 1)
    waiting = hold(store, staging, T0 + 2).body["job_id"]
    leases.expire(store, T0 + 2 + node_hold.LEASE_S + 1)
    assert turn(store, staging, waiting, T0 + 200)["ended"] == "its dev machine went quiet"


def test_a_held_node_goes_back_after_its_time_or_its_lease(store, staging):
    node(store, staging)
    job_id = held(store, staging, for_s=60)
    said = turn(store, staging, job_id, T0 + 62)
    assert (said["state"], said["ended"]) == ("finished", "its time was up")
    again = held(store, staging, T0 + 70)
    leases.expire(store, T0 + 70 + node_hold.LEASE_S + 1)
    with store.read() as conn:
        assert st.require_job(conn, again)["outcome"] == "interrupted"


def test_cancel_lets_go_and_a_worker_restart_does_not(store, staging):
    node(store, staging)
    job_id = held(store, staging)
    node(store, staging, T0 + 2, restarted=True)
    with store.read() as conn:
        assert st.require_job(conn, job_id)["state"] == "running"
    said = call(store, staging, "cancel", T0 + 3, job_id=job_id).body
    assert said["state"] == "finished"


def test_an_upgrade_waits_for_the_hold(store, staging):
    node(store, staging)
    job_id = held(store, staging)
    up = call(store, staging, "upgrade", T0 + 2, action="queue", worker="wrk-a",
              version="9.9.9").body
    assert not call(store, staging, "upgrade", T0 + 3, action="turn", job_id=up["job_id"]).body["go"]
    call(store, staging, "hold", T0 + 4, action="release", job_id=job_id)
    assert call(store, staging, "upgrade", T0 + 5, action="turn", job_id=up["job_id"]).body["go"]
