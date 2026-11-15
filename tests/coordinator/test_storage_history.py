"""Every node's cleanups, kept and read back (coordinator/storage_history.py), and the `sweep`
order that runs one now (coordinator/project_orders.py)."""

from mulebox.common.protocol import MessageType
from mulebox.coordinator import api, storage_history

from .helpers import request


def report(at, started, count=1):
    return {"at": at, "disk": {"total": 10, "free": 5, "reserve": 1}, "projects": [],
            "sweep": {"started": started, "trigger": "hourly", "count": count, "bytes": 700,
                      "removed": [{"project": "example-app", "folder": "f", "size": 700,
                                   "why": "gone"}]}}


def claim(store, staging, now, worker="build-1", **extra):
    return api.handle(store, staging, request("claim", worker=worker, capabilities=[],
                                              free_slots=1, **extra), now)


def test_each_sweep_is_kept_once_and_read_back_newest_first(store, staging):
    claim(store, staging, 1.0, storage=report(2.0, 1.5))
    claim(store, staging, 3.0, storage=report(2.0, 1.5))  # the same sweep again
    claim(store, staging, 4.0, storage=report(5.0, 4.5, count=0))
    history = api.handle(store, staging, request("storage"), 6.0).body["history"]
    assert [(h["node"], h["started"], h["count"]) for h in history] == [
        ("build-1", 4.5, 0), ("build-1", 1.5, 1)]
    assert history[1]["removed"][0]["why"] == "gone"


def test_only_the_newest_are_kept(store, staging, monkeypatch):
    monkeypatch.setattr(storage_history, "KEEP", 2)
    for n in range(4):
        claim(store, staging, 10.0 + n, storage=report(10.0 + n, 10.0 + n))
    history = api.handle(store, staging, request("storage", history=10), 20.0).body["history"]
    assert [h["started"] for h in history] == [13.0, 12.0]


def test_run_now_goes_to_the_node_asked_for(store, staging):
    claim(store, staging, 1.0, worker="build-1")
    claim(store, staging, 1.0, worker="build-2")
    reply = api.handle(store, staging, request("project_order", action="sweep", node="build-2",
                                               docker=True), 2.0)
    assert reply.type is MessageType.PROJECT_ORDER_OK and reply.body["nodes"] == ["build-2"]
    orders = claim(store, staging, 3.0, worker="build-2").body["orders"]
    assert orders[0]["action"] == "sweep" and orders[0]["docker"] is True
    assert "orders" not in claim(store, staging, 3.0, worker="build-1").body
    refused = api.handle(store, staging, request("project_order", action="sweep", node="nope"),
                         4.0)
    assert refused.type is MessageType.ERROR


def test_a_node_over_its_warning_size_is_named_to_every_command(store, staging):
    over = {**report(1.0, 0.5), "held": 60 * 10**9, "policy": {"warn_size": "50GB"}}  # before 1.30
    claim(store, staging, 1.0, storage=over)
    from mulebox.coordinator import storage
    with store.read() as conn:
        assert storage.heavy(conn, 2.0) == [{"worker": "build-1", "held": 60 * 10**9,
                                             "warn": 50 * 10**9, "max": None}]
    claim(store, staging, 2.0, storage={**over, "held": 17 * 10**9, "at": 3.0,
                                        "policy": {"max_size": "20GB", "warn_size": "16GB"}})
    with store.read() as conn:  # from 1.30: 80% of the space mulebox may use
        assert storage.heavy(conn, 3.0) == [{"worker": "build-1", "held": 17 * 10**9,
                                             "warn": 16 * 10**9, "max": 20 * 10**9}]
    claim(store, staging, 3.0, storage={**over, "at": 4.0, "policy": {"warn_size": "OFF"}})
    with store.read() as conn:
        assert storage.heavy(conn, 4.0) == []
