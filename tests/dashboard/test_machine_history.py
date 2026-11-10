"""Other machines' graphs: the history kept per worker, `/api/metrics?machine=`, `host` and
`version` on the machines panel."""

import asyncio

from aiohttp.test_utils import TestClient, TestServer

from mulebox.coordinator import api
from mulebox.dashboard.data import DashboardData
from mulebox.dashboard.events import EventBus
from mulebox.dashboard.hub import Hub
from mulebox.dashboard.machine_history import MAX_ENTRIES, WINDOW_S, MachineHistory, entry
from mulebox.dashboard.server import build_app
from tests.coordinator.helpers import request

from .conftest import NOW, FakeSampler, no_docker

LOAD = {"cpu_pct": 50.0, "cpu": [40.0, 60.0], "memory": {"total": 8, "available": 6, "used": 2},
        "disk": {"roots": ["jobs"], "total": 100, "used": 40, "free": 60}}


def worker(name="build-2", seen=NOW, load=LOAD):
    return {"worker": name, "last_seen": seen, "load": load}


def test_an_entry_has_the_hosts_shape_without_its_own_parts():
    assert entry(worker()) == {"t": NOW, "cpu": [40.0, 60.0], "memory": LOAD["memory"],
                               "disk": [LOAD["disk"]]}
    assert entry(worker(load={"cpu_pct": 5.0})) == {"t": NOW, "cpu": [], "memory": None,
                                                    "disk": []}  # a worker before these readings


def test_one_entry_per_report_bounded_by_five_minutes():
    history = MachineHistory()
    history.record([worker(seen=NOW)], NOW)
    history.record([worker(seen=NOW + 0.5)], NOW + 1)  # too close: the same reading
    history.record([worker(seen=NOW + 2)], NOW + 2)
    assert [e["t"] for e in history.reply("build-2", NOW + 2)["history"]] == [NOW, NOW + 2]
    for step in range(1, 400):
        t = NOW + 2 + step * 2
        history.record([worker(seen=t)], t)
    kept = history.reply("build-2", t)["history"]
    assert len(kept) <= MAX_ENTRIES and kept[0]["t"] >= t - WINDOW_S and kept[-1]["t"] == t


def test_offline_unknown_and_forgotten_machines():
    history = MachineHistory()
    history.record([worker(seen=NOW)], NOW)
    assert history.reply("build-2", NOW + 60) == {"machine": "build-2", "host": False,
                                                  "last_seen": NOW, "history": []}
    assert history.reply("nope", NOW) is None
    history.record([], NOW + 1)  # removed from the store
    assert not history.knows("build-2")


def _metrics(store, staging, *urls, local_name="wrk-a"):
    """Claims from wrk-a (this machine) and build-2, one machines step, then GET each url."""
    for name, load in (("wrk-a", None), ("build-2", LOAD)):
        api.handle(store, staging, request("claim", worker=name, capabilities=[], free_slots=1,
                                           version="0.9.0", **({"load": load} if load else {})),
                   NOW)
    data = DashboardData(store, staging, local_name=local_name)
    hub = Hub(data, EventBus(epoch="test"), {}, sampler=FakeSampler(), docker_count=no_docker,
              clock=lambda: NOW)

    async def go():
        await hub.machines_step()
        await hub.metrics_step()
        app = build_app(data, hub, clock=lambda: NOW, start_hub=False)
        async with TestClient(TestServer(app)) as client:
            out = []
            for url in urls:
                reply = await client.get(url)
                out.append((reply.status, await reply.json() if reply.status == 200 else None))
            return out
    return asyncio.run(go())


def test_metrics_for_this_machine_another_one_and_an_unknown_name(store, staging):
    (bare, own), (host, again), (other_status, other), (missing, _) = _metrics(
        store, staging, "/api/metrics", "/api/metrics?machine=wrk-a",
        "/api/metrics?machine=build-2", "/api/metrics?machine=nope")
    assert bare == host == other_status == 200 and missing == 404
    assert own["machine"] == "wrk-a" and own["host"] is True and own["history"][0]["self"]
    assert again["history"] == own["history"]
    assert other == {"machine": "build-2", "host": False, "last_seen": NOW,
                     "history": [{"t": NOW, "cpu": [40.0, 60.0], "memory": LOAD["memory"],
                                  "disk": [LOAD["disk"]]}]}


def test_machines_rows_say_which_is_the_host_and_their_version(store, staging):
    [(status, body)] = _metrics(store, staging, "/api/machines")
    rows = {row["name"]: row for row in body["machines"]}
    assert status == 200 and rows["wrk-a"]["host"] is True and rows["build-2"]["host"] is False
    assert {row["version"] for row in rows.values()} == {"0.9.0"}
    [(_, body)] = _metrics(store, staging, "/api/machines", local_name=None)
    assert not any(row["host"] for row in body["machines"])  # no worker on the dashboard's machine
