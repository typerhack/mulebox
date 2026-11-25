"""A node that rests, on the coordinator (coordinator/health.py), with the real store and API."""

from mulebox.common.protocol import MessageType
from mulebox.coordinator import health, needs, workers

from .helpers import queued, request, submit_body
from .test_api import T0, call
from mulebox.coordinator import api

DOCKER_DOWN = {"resting": False, "until": None, "round": 4, "withheld": ["compose-v1", "docker"],
               "problems": [{"check": "docker", "message": "Docker does not answer",
                             "fix": "start Docker on build-1", "since": T0}]}
DISK_LOW = {"resting": True, "until": None, "round": 2, "withheld": [],
            "problems": [{"check": "disk", "message": "1.0 GB free",
                          "fix": "`mulebox storage clean`", "since": T0}]}


def claim(store, staging, now=T0, worker="build-1", capabilities=("node", "linux"), **body):
    return call(store, staging, "claim", now=now, worker=worker, capabilities=list(capabilities),
                free_slots=body.pop("free_slots", 1), version=body.pop("version", "1.41.0"),
                **body)


def row(store, name="build-1"):
    with store.read() as conn:
        return workers.get(conn, name)


def test_a_claim_keeps_health_and_withheld_capabilities_still_count_at_submit(store, staging):
    claim(store, staging, health=DOCKER_DOWN)
    found = row(store)
    assert health.of(found)["withheld"] == ["compose-v1", "docker"]
    assert "docker" in found["capabilities"] and "docker" not in health.offers(found)
    reply = call(store, staging, "submit", **submit_body(needs=["docker"]))
    assert reply.type is MessageType.SUBMIT_OK  # a passing fault refuses no job
    reply = claim(store, staging, health={**DOCKER_DOWN, "problems": [], "withheld": []})
    assert health.of(row(store))["problems"] == []
    claim(store, staging)  # an older worker sends no health: what it said stays
    assert health.of(row(store))["round"] == 4


def test_a_resting_node_keeps_its_slots_and_no_peer_waits_for_it(store, staging):
    claim(store, staging, worker="build-2", free_slots=0, slots=3, health=DISK_LOW)
    assert row(store, "build-2")["slots"] == 3 and health.resting(row(store, "build-2"))
    with store.read() as conn:
        assert workers.cluster_limit(conn, T0, 1) == 3
    queued(store, staging, now=T0)
    reply = claim(store, staging, now=T0 + 1)  # build-2 ranks no higher, but is not free anyway
    assert reply.type is MessageType.CLAIM_OK


def test_the_waiting_reason_names_the_fault_and_the_fix():
    rows = [{"worker": "build-1", "capabilities": ["docker", "linux"], "last_seen": T0,
             "health": DOCKER_DOWN}]
    text = needs.waiting_for(rows, ["docker", "linux"], T0)
    assert text.startswith("build-1 holds back some jobs: Docker does not answer (since ")
    assert "start Docker on build-1" in text and "`mulebox machine check <node>`" in text
    assert needs.waiting_for(rows, ["linux"], T0) is None  # it still takes jobs without Docker
    rows[0]["health"] = DISK_LOW
    assert needs.waiting_for(rows, ["linux"], T0).startswith("build-1 is resting: 1.0 GB free")


def started(store, staging, job_id, now=T0):
    reply = claim(store, staging, now=now)
    assert reply.type is MessageType.CLAIM_OK and reply.body["job_id"] == job_id
    ids = {"job_id": job_id, "attempt_id": reply.body["attempt_id"]}
    call(store, staging, "log_chunk", now=now, offset=0, data="first try\n", **ids)
    call(store, staging, "job_update", now=now, state="cleaning", **ids)
    return ids, reply.body


def failed(store, staging, ids, **body):
    return call(store, staging, "result", outcome="failed", exit_code=None, duration_s=1.0,
                **ids, **body)


def test_a_job_its_node_could_not_set_up_goes_back_in_line_once(store, staging):
    job_id = queued(store, staging)
    ids, _ = started(store, staging, job_id)
    reply = failed(store, staging, ids, node_fault="build-1 could not set it up: 1.0 GB free")
    assert reply.body["state"] == "queued" and reply.body["cancel"] is False
    job = store.get_job(job_id)
    assert job["retries"] == 1 and job["worker"] is None and job["attempt_id"] is None
    log = staging.log_path(job_id).read_text()
    assert log.startswith("first try\nmulebox: build-1 could not set it up: 1.0 GB free.")
    assert "it is not your code" in log and job["log_size"] == len(log.encode())
    old = claim(store, staging, now=T0 + 1, worker="build-old", version="1.40.3")
    assert old.type is MessageType.CLAIM_NONE  # it would not go on with the log
    ids, body = started(store, staging, job_id, now=T0 + 2)
    assert body["log_offset"] == job["log_size"]
    reply = failed(store, staging, ids, node_fault="build-1 could not set it up again")
    assert reply.body["state"] == "finished" and store.get_job(job_id)["exit_code"] is None


def test_a_failure_with_no_node_fault_or_with_a_command_ends_the_job(store, staging):
    for body in ({}, {"node_fault": ""}):
        job_id = queued(store, staging)
        ids, _ = started(store, staging, job_id)
        assert failed(store, staging, ids, **body).body["state"] == "finished"
    job_id = queued(store, staging)
    ids, _ = started(store, staging, job_id)
    reply = call(store, staging, "result", outcome="failed", exit_code=1, duration_s=1.0,
                 node_fault="x", **ids)
    assert reply.body["state"] == "finished"


def test_a_cancelled_job_does_not_go_back(store, staging):
    job_id = queued(store, staging)
    ids, _ = started(store, staging, job_id)
    call(store, staging, "cancel", job_id=job_id)
    assert failed(store, staging, ids, node_fault="x").body["state"] == "finished"


def test_machine_check_is_handed_to_the_node_once(store, staging):
    claim(store, staging)
    reply = api.handle(store, staging, request("machine", worker="build-1", action="check"), T0)
    assert reply.type is MessageType.MACHINE_OK
    assert claim(store, staging, now=T0 + 1).body.get("health_check") is True
    assert "health_check" not in claim(store, staging, now=T0 + 2).body
    api.handle(store, staging, request("machine", worker="build-1", action="check"), T0)
    assert "health_check" not in claim(store, staging, now=T0 + health.CHECK_WAIT_S + 1).body


def test_a_broken_report_never_fails_a_claim(store, staging):
    for bad in ("resting", {"problems": "x"}, {"problems": [{"check": "nope"}]}, None):
        assert claim(store, staging, health=bad).type is MessageType.CLAIM_NONE


def test_a_runner_supervisor_s_heartbeat_leaves_the_ask_for_the_worker(store, staging):
    from .test_reservations import acquire, reserve
    claim(store, staging)
    slot = reserve(store, staging)
    assert acquire(store, staging, slot)["state"] == "running"
    api.handle(store, staging, request("machine", worker="build-1", action="check"), T0)
    beat = call(store, staging, "heartbeat", now=T0 + 1, job_id=slot, lease="worker")
    assert "health_check" not in beat.body
    assert claim(store, staging, now=T0 + 2).body.get("health_check") is True


def test_a_waiting_job_names_the_nodes_that_hold_it():
    from mulebox.coordinator import views
    fleet = [{"worker": "build-1", "capabilities": ["linux"], "last_seen": T0, "health": DISK_LOW},
             {"worker": "build-2", "capabilities": ["docker", "linux"], "last_seen": T0,
              "health": DOCKER_DOWN}]
    job = {"kind": "job", "state": "queued", "needs": ["linux"], "pinned_worker": None}
    assert "held_by" not in views.placement(fleet, job, T0)  # build-2 takes it
    docker = {**job, "needs": ["docker", "linux"]}
    assert views.placement(fleet, docker, T0)["held_by"] == ["build-2"]
    assert needs.held_by(fleet[:1], ["linux"], T0) == ["build-1"]
    assert needs.held_by(fleet[:1], ["linux"], T0 + 3600) == []  # offline: not its health


def test_the_report_keeps_what_the_dashboard_shows_and_drops_the_rest():
    from mulebox.common import node_health
    found = node_health.checked({**DISK_LOW, "ran": ["git", "disk", "nope"], "checked_at": T0,
                                 "next_at": "soon", "min_free": 5 * 10**9})
    assert found["ran"] == ["disk", "git"] and found["checked_at"] == T0
    assert "next_at" not in found and found["min_free"] == 5 * 10**9
    assert "ran" not in node_health.checked(DISK_LOW)  # an older worker's
