import threading

from mulebox.common.protocol import Outcome
from mulebox.coordinator import daemon, leases

from .helpers import claimed, queued

T0 = 1000.0


def test_run_recovers_then_sweeps(store, staging):
    stale = claimed(store, staging, now=T0)
    waiting = queued(store, staging, now=T0)
    stop = threading.Event()
    times = iter([T0 + leases.WORKER_LEASE_S + 1, T0 + 10_000, T0 + 10_005])

    def clock():
        value = next(times)
        if value >= T0 + 10_005:
            stop.set()
        return value

    sweeps = daemon.run(store, staging, stop, clock=clock, interval=0)
    assert sweeps == 2
    assert store.get_job(stale["job_id"])["outcome"] == Outcome.INTERRUPTED
    assert store.get_job(waiting)["state"] == "queued"  # a queued job is never stopped


def test_sweep_errors_do_not_stop_the_loop(store, staging, monkeypatch):
    stop = threading.Event()
    calls = []

    def failing(*args):
        calls.append(args)
        if len(calls) == 2:
            stop.set()
        raise RuntimeError("disk hiccup")

    monkeypatch.setattr(daemon.leases, "expire", failing)
    assert daemon.run(store, staging, stop, clock=lambda: T0, interval=0) == 2


def test_serve_opens_and_closes(node):
    stop = threading.Event()
    stop.set()
    assert daemon.serve(node, stop) == 0
