"""`mulebox coordinator serve`: recovery first, then a lease sweep every 5 s.

Requests do not go through this process (each `mulebox rpc` opens the store itself); the
service only applies time-based rules. SIGTERM and SIGINT end the loop cleanly.
"""

import signal
import threading
import time
from collections.abc import Callable

from mulebox.common.config import NodeConfig
from mulebox.common.log import get_logger
from mulebox.coordinator import leases, recovery
from mulebox.coordinator.node import open_local
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store

_log = get_logger(__name__)
SWEEP_S = 5.0


def run(store: Store, staging: Staging, stop: threading.Event, *,
        clock: Callable[[], float] = time.time, interval: float = SWEEP_S) -> int:
    """Recovery, then sweep until `stop` is set; return the number of sweeps done."""
    interrupted = recovery.recover(store, clock(), staging)
    _log.info("recovery done: %d job(s) interrupted", len(interrupted))
    sweeps = 0
    while not stop.is_set():
        try:
            finished = leases.expire(store, clock(), staging)
            if finished:
                _log.info("lease sweep finished %d job(s): %s", len(finished), ", ".join(finished))
        except Exception:  # noqa: BLE001 - one failed sweep must not stop the service
            _log.exception("lease sweep failed")
        sweeps += 1
        stop.wait(interval)
    return sweeps


def serve(node: NodeConfig, stop: threading.Event | None = None) -> int:
    """Run the coordinator service for `node` until SIGTERM; return the exit code."""
    stop = stop or threading.Event()
    previous = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, lambda *_: stop.set())
    store, staging = open_local(node)
    try:
        _log.info("coordinator %s serving (store %s)", node.name, store.path)
        run(store, staging, stop)
    finally:
        store.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    _log.info("coordinator stopped")
    return 0
