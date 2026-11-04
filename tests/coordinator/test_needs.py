"""A job no worker can run is refused or says why it waits; it never just sits in the queue."""

import io

from mulebox.client import queue_view, report
from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import api, needs, queue, watch

from .helpers import queued, request, submit_body

NOW = 1000.0


def worker(name="build-1", capabilities=(), seen=NOW):
    return {"worker": name, "capabilities": list(capabilities), "last_seen": seen}


def seen(store, name="build-1", capabilities=(), at=NOW):
    queue.claim(store, name, list(capabilities), 1, 1, now=at)


def test_a_job_with_needs_nobody_offers_is_refused_at_submit(store, staging):
    seen(store, capabilities=["node"])
    msg = request("submit", **submit_body(needs=["docker"]))
    reply = api.handle(store, staging, msg, NOW)
    assert reply.type is MessageType.ERROR and reply.body["code"] == "no_worker"
    text = reply.body["message"]
    assert "docker" in text and "build-1 offers node" in text
    assert "capabilities" in text and "node.toml" in text
    with store.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_refusal_says_when_a_machine_offers_nothing():
    assert "build-1 offers nothing" in needs.refusal([worker()], ["docker"])


def test_a_job_is_accepted_when_any_worker_offers_its_needs_even_offline():
    workers = [worker("a"), worker("b", ["docker"], seen=0.0)]
    assert needs.refusal(workers, ["docker"]) is None


def test_nothing_is_refused_before_any_worker_was_seen():
    assert needs.refusal([], ["docker"]) is None


def test_no_needs_is_never_refused():
    assert needs.refusal([worker()], []) is None


def test_an_idempotent_resubmit_returns_the_job_even_if_the_worker_changed(store, staging):
    body = submit_body(needs=["docker"], idempotency_key="sub-same")
    seen(store, capabilities=["docker"])
    first = api.handle(store, staging, request("submit", **body), NOW)
    seen(store, capabilities=[], at=NOW + 1)
    again = api.handle(store, staging, request("submit", **body), NOW + 1)
    assert again.body["job_id"] == first.body["job_id"]


def test_capable_workers_are_those_covering_the_needs_online_or_not():
    fleet = [worker("a", ["node"]), worker("b", ["node", "docker"], seen=0.0), worker("c")]
    assert [w["worker"] for w in needs.capable(fleet, ["docker"])] == ["b"]
    assert [w["worker"] for w in needs.capable(fleet, [])] == ["a", "b", "c"]
    assert needs.capable(fleet, ["gpu"]) == []


def test_online_capable_worker_is_no_reason_to_wait():
    assert needs.waiting_for([worker(capabilities=["docker"])], ["docker"], NOW) is None


def test_offline_capable_worker_is_named():
    workers = [worker("a", ["docker"], seen=NOW - 100), worker("b")]
    text = needs.waiting_for(workers, ["docker"], NOW)
    assert "offline: a" in text and "b" not in text.split("offline:")[1]


def test_no_worker_at_all_is_a_reason():
    assert "no build machine has connected" in needs.waiting_for([], [], NOW)


def test_needs_that_went_away_after_queueing_are_explained():
    text = needs.waiting_for([worker(capabilities=["node"])], ["docker"], NOW)
    assert "no build machine offers docker" in text


def status_of(store, staging, job_id, now):
    return api.handle(store, staging, request("status", job_id=job_id), now).body


def test_status_says_why_a_queued_job_waits_and_stops_once_it_can_run(store, staging):
    seen(store, capabilities=["docker"])
    job_id = queued(store, staging, needs=["docker"], now=NOW)
    assert "waiting_for" not in status_of(store, staging, job_id, NOW)
    assert "offline" in status_of(store, staging, job_id, NOW + 100)["waiting_for"]


def test_queue_listing_carries_the_reason(store, staging):
    seen(store, capabilities=["docker"], at=NOW)
    queued(store, staging, needs=["docker"], now=NOW)
    reply = api.handle(store, staging, request("queue"), NOW + 100)
    assert "offline" in reply.body["jobs"][0]["waiting_for"]
    lines = queue_view.render_table(reply.body["jobs"], NOW + 100)
    assert any(line.startswith("  waiting: ") and "offline" in line for line in lines)


def test_the_client_prints_the_reason():
    line = report.state_line({"state": "queued", "position": 1, "waiting_for": "x is offline"})
    assert line == "queued, position 1; waiting: x is offline"
    assert report.state_line({"state": "queued", "position": 1}) == "queued, position 1"


def test_the_watch_stream_sends_the_reason_when_it_changes(store, staging):
    seen(store, capabilities=["docker"], at=NOW)
    job_id = queued(store, staging, needs=["docker"], now=NOW)
    times = iter([NOW, NOW, NOW + 1, NOW + 100, NOW + 101])
    out = io.BytesIO()

    class Done(Exception):
        pass

    def stop(_):
        if len(out.getvalue().splitlines()) >= 2:
            raise Done

    msg = Message(MessageType.WATCH, "req-w", {"job_id": job_id, "offset": 0, "lease": False})
    try:
        watch.watch(store, staging, msg, io.BytesIO(), out, clock=lambda: next(times), sleep=stop)
    except Done:
        pass
    assert b"waiting_for" in out.getvalue().splitlines()[-1]


COMPOSE_NEEDS = ["docker", "compose-v1"]


def test_an_older_worker_with_docker_is_not_offered_a_compose_job():
    text = needs.refusal([worker(capabilities=["docker"])], COMPOSE_NEEDS)
    assert "compose-v1" in text and "upgrade" in text and "capabilities" not in text.split(":")[1]


def test_a_worker_without_docker_is_told_how_to_add_it():
    text = needs.refusal([worker(capabilities=["node"])], COMPOSE_NEEDS)
    assert "add it to `capabilities`" in text and "upgrade" not in text


def test_a_current_worker_runs_a_compose_job():
    workers = [worker(capabilities=["docker", "compose-v1"])]
    assert needs.refusal(workers, COMPOSE_NEEDS) is None
    assert needs.waiting_for(workers, COMPOSE_NEEDS, NOW) is None


def test_a_mixed_fleet_waits_for_the_current_worker():
    workers = [worker("old", ["docker"]), worker("new", ["docker", "compose-v1"], seen=0.0)]
    assert needs.refusal(workers, COMPOSE_NEEDS) is None
    assert "offline: new" in needs.waiting_for(workers, COMPOSE_NEEDS, NOW)


def test_an_older_queued_job_says_upgrade_while_it_waits():
    assert "upgrade" in needs.waiting_for([worker(capabilities=["docker"])], COMPOSE_NEEDS, NOW)


OLD_CLIENT = {"needs": ["docker"], "env": {"MULEBOX_COMPOSE_FILES": "docker-compose.yml"}}


def test_the_coordinator_adds_what_an_older_client_left_out():
    assert needs.required(["docker"], OLD_CLIENT["env"]) == ["docker", "compose-v1"]
    assert needs.required([], OLD_CLIENT["env"]) == ["docker", "compose-v1"]
    assert needs.required(["node", "compose-v1", "docker"], OLD_CLIENT["env"]) == [
        "node", "compose-v1", "docker"]


def test_a_job_without_compose_needs_only_what_it_says():
    assert needs.required(["docker"], {"CI": "1"}) == ["docker"]


def test_an_older_client_cannot_reach_an_older_worker(store, staging):
    seen(store, capabilities=["docker"])
    reply = api.handle(store, staging, request("submit", **submit_body(**OLD_CLIENT)), NOW)
    assert reply.type is MessageType.ERROR and reply.body["code"] == "no_worker"
    assert "upgrade" in reply.body["message"]


def test_an_older_client_gets_a_current_worker(store, staging):
    seen(store, capabilities=["docker", "compose-v1"])
    reply = api.handle(store, staging, request("submit", **submit_body(**OLD_CLIENT)), NOW)
    assert reply.type is MessageType.SUBMIT_OK
    with store.read() as conn:
        stored = conn.execute("SELECT needs FROM jobs").fetchone()[0]
    assert "compose-v1" in stored


def test_with_no_worker_seen_a_stored_job_still_needs_it(store, staging):
    api.handle(store, staging, request("submit", **submit_body(**OLD_CLIENT)), NOW)
    with store.read() as conn:
        assert "compose-v1" in conn.execute("SELECT needs FROM jobs").fetchone()[0]
