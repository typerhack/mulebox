"""The machines panel: the rules, then the real path from claim to event."""

import asyncio

from mulebox.coordinator import api, workers
from mulebox.dashboard import machines
from mulebox.dashboard.machines import AVAILABLE, BUSY, OFFLINE, OFFLINE_AFTER_S
from tests.coordinator.helpers import request

from .conftest import NOW


def worker(name="wrk-a", slots=2, seen=NOW, free=2):
    return {"worker": name, "slots": slots, "last_seen": seen, "free_slots": free,
            "capabilities": ["docker"]}


def job(name="wrk-a", job_id="job-1"):
    return {"job_id": job_id, "project": "example-app", "job": "check", "kind": "job",
            "worker": name, "env": {"SECRET": "x"}, "argv": ["secret"]}


def test_free_slots_come_from_jobs_not_the_stale_stored_value():
    row = machines.machine(worker(free=2), [job()], NOW)
    assert row["state"] == AVAILABLE and row["free_slots"] == 1


def test_full_machine_is_busy_with_nothing_free():
    row = machines.machine(worker(slots=1, free=1), [job()], NOW)
    assert row["state"] == BUSY and row["free_slots"] == 0


def test_quiet_machine_is_offline_and_offers_nothing():
    quiet = worker(seen=NOW - OFFLINE_AFTER_S - 1)
    row = machines.machine(quiet, [], NOW)
    assert row["state"] == OFFLINE and row["free_slots"] == 0
    assert machines.machine(worker(seen=NOW - OFFLINE_AFTER_S), [], NOW)["state"] == AVAILABLE


def test_draining_machine_offers_nothing_new():
    row = machines.machine({**worker(), "draining": 1}, [job()], NOW)
    assert row["state"] == machines.DRAINING and row["free_slots"] == 0


def test_slots_unknown_from_an_old_row_still_gives_a_sane_answer():
    assert machines.machine(worker(slots=None), [], NOW)["slots"] == 1
    assert machines.machine(worker(slots=None), [job()], NOW)["free_slots"] == 0


def test_job_rows_carry_only_what_the_panel_shows():
    shown = machines.machine(worker(), [job()], NOW)["jobs"][0]
    assert set(shown) == {"job_id", "project", "job", "kind"}


def test_summary_counts_the_cluster_and_keeps_each_job_on_its_machine():
    panel = machines.snapshot(
        [worker("a"), worker("b", seen=0.0), worker("c", slots=1)],
        [job("a"), job("c", "job-2")], NOW)
    assert (panel["total"], panel["online"], panel["free_slots"]) == (3, 2, 1)
    assert [len(row["jobs"]) for row in panel["machines"]] == [1, 0, 1]


def test_rows_carry_no_readings_until_something_measures_them():
    row = machines.machine(worker(), [], NOW)
    assert row["cpu_pct"] is None and row["mem_pct"] is None


def test_readings_come_from_a_metrics_sample_or_stay_null():
    sample = {"cpu": [10.0, 30.0], "memory": {"total": 200, "available": 50, "used": 150}}
    assert machines.readings(sample) == {"cpu_pct": 20.0, "mem_pct": 75.0, "cores": 2}
    none = {"cpu_pct": None, "mem_pct": None, "cores": None}
    assert machines.readings({"cpu": None, "memory": None}) == none
    assert machines.readings(None) == none


def test_only_the_named_machine_gets_the_dashboard_hosts_readings():
    panel = machines.snapshot([worker("a"), worker("b")], [], NOW)
    machines.with_readings(panel, "b", {"cpu": [50.0], "memory": {"total": 10, "used": 1}})
    rows = {row["name"]: row for row in panel["machines"]}
    assert rows["b"]["cpu_pct"] == 50.0 and rows["b"]["mem_pct"] == 10.0
    assert rows["a"]["cpu_pct"] is None and rows["a"]["mem_pct"] is None
    machines.with_readings(panel, "nobody", {"cpu": [1.0], "memory": None})  # changes nothing
    assert rows["a"]["cpu_pct"] is None


def test_fingerprint_sees_a_reading_move_a_whole_percent_only():
    def panel(cpu):
        out = machines.snapshot([worker()], [], NOW)
        return machines.with_readings(out, "wrk-a", {"cpu": [cpu], "memory": None})
    assert machines.fingerprint(panel(10.2)) == machines.fingerprint(panel(10.4))
    assert machines.fingerprint(panel(10.2)) != machines.fingerprint(panel(11.0))


def test_fingerprint_ignores_time_passing_but_sees_a_state_change():
    first = machines.snapshot([worker()], [], NOW)
    assert machines.fingerprint(first) == machines.fingerprint(
        machines.snapshot([worker(seen=NOW + 1)], [], NOW + 1))
    assert machines.fingerprint(first) != machines.fingerprint(
        machines.snapshot([worker(seen=0.0)], [], NOW))


def test_busy_one_slot_worker_stays_online_through_its_heartbeats(store, staging, data, run_job):
    """A busy worker sends no claims, so only heartbeats can keep it online."""
    job_id, state = run_job()
    later = NOW + OFFLINE_AFTER_S * 10
    assert data.machines(later)["machines"][0]["state"] == OFFLINE
    reply = api.handle(store, staging, request("heartbeat", lease="worker", **state), later)
    assert "error" not in reply.body, reply.body
    row = data.machines(later)["machines"][0]
    assert row["state"] == BUSY and row["free_slots"] == 0
    assert row["jobs"][0]["job_id"] == job_id


def test_worker_that_stops_heartbeating_goes_offline(store, staging, data, run_job):
    run_job()
    panel = data.machines(NOW + OFFLINE_AFTER_S + 1)
    assert panel["online"] == 0 and panel["machines"][0]["state"] == OFFLINE


def test_touch_never_invents_a_worker(store):
    with store.write() as conn:
        workers.touch(conn, "nobody", NOW)
        workers.touch(conn, None, NOW)
        assert workers.listing(conn) == []


def test_hub_publishes_only_on_change_including_going_quiet(hub, run_job):
    run_job()

    async def go():
        assert await hub.machines_step() is True
        assert await hub.machines_step() is False
        hub.clock = lambda: NOW + OFFLINE_AFTER_S + 1
        assert await hub.machines_step() is True
    asyncio.run(go())
    assert hub.current_machines()["machines"][0]["state"] == OFFLINE


def test_hub_fills_the_local_machines_readings_and_nothing_else(hub, store, run_job):
    """The dashboard's own sampler (FakeSampler: cores at 10 and 20, memory 40 of 100) is
    the only source today; the hub puts it on the row named after this machine."""
    run_job()  # wrk-a
    with store.write() as conn:
        workers.upsert(conn, "wrk-b", [], 1, NOW, slots=1)
    hub.local_name = "wrk-a"

    async def go():
        await hub.metrics_step()
        assert await hub.machines_step() is True
        assert await hub.machines_step() is False  # same readings, no event
    asyncio.run(go())
    rows = {row["name"]: row for row in hub.current_machines()["machines"]}
    assert rows["wrk-a"]["cpu_pct"] == 15.0 and rows["wrk-a"]["mem_pct"] == 40.0
    assert rows["wrk-b"]["cpu_pct"] is None and rows["wrk-b"]["mem_pct"] is None


def test_machines_route_serves_the_hubs_panel_with_readings(call, hub, run_job):
    run_job()
    hub.local_name = "wrk-a"

    async def go(client):
        await hub.metrics_step()
        await hub.machines_step()
        return await (await client.get("/api/machines")).json()
    body = call(go)
    assert body["machines"][0]["cpu_pct"] == 15.0


def test_route_and_event_stream_snapshot(call, run_job):
    run_job()

    async def go(client):
        body = await (await client.get("/api/machines")).json()
        reply = await client.get("/api/events")
        text = (await reply.content.read(4096)).decode()
        return body, text
    body, text = call(go)
    assert body["total"] == 1 and body["machines"][0]["name"] == "wrk-a"
    assert "event: machines" in text
