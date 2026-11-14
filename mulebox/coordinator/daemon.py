"""`mulebox coordinator serve`: recovery first, then a lease sweep every 5 s, and retention
(old logs, retention.py) at the start and once an hour.

Requests do not go through this process (each `mulebox rpc` opens the store itself); the
service only applies time-based rules. SIGTERM and SIGINT end the loop cleanly.
"""

import signal
import threading
import time
from collections.abc import Callable

from mulebox.common.config import DEFAULT_LOG_DAYS, DEFAULT_STEP_DAYS, NodeConfig
from mulebox.common.log import get_logger
from mulebox.coordinator import attendance, leases, recovery, retention, workers
from mulebox.coordinator.node import open_local
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store

_log = get_logger(__name__)
SWEEP_S = 5.0
RETENTION_S = 3600.0
LOG_DAYS, STEP_DAYS = DEFAULT_LOG_DAYS, DEFAULT_STEP_DAYS


def run(store: Store, staging: Staging, stop: threading.Event, *,
        clock: Callable[[], float] = time.time, interval: float = SWEEP_S,
        log_days: int = LOG_DAYS, step_days: int = STEP_DAYS) -> int:
    """Recovery, then sweep until `stop` is set; return the number of sweeps done."""
    interrupted = recovery.recover(store, clock(), staging)
    _log.info("recovery done: %d job(s) interrupted", len(interrupted))
    sweeps = 0
    next_retention = 0.0
    while not stop.is_set():
        now = clock()
        if now >= next_retention:
            next_retention = now + RETENTION_S
            _keep_tidy(store, staging, now, log_days, step_days)
        try:
            finished = leases.expire(store, now, staging)
            if finished:
                _log.info("lease sweep finished %d job(s): %s", len(finished), ", ".join(finished))
        except Exception:  # noqa: BLE001 - one failed sweep must not stop the service
            _log.exception("lease sweep failed")
        sweeps += 1
        stop.wait(interval)
    return sweeps


def _keep_tidy(store: Store, staging: Staging, now: float, log_days: int, step_days: int) -> None:
    try:
        logs, rows = retention.sweep(store, staging, now, log_days, step_days)
        if logs or rows:
            _log.info("retention removed %d log(s) and %d stage row(s)", logs, rows)
    except Exception:  # noqa: BLE001 - tidying up must never stop the service
        _log.exception("retention failed")


def limits_of(node: NodeConfig) -> attendance.Limits:
    """The machine's `[limits]`, the defaults when the node has none."""
    if not node.limits:
        return attendance.Limits()
    return attendance.Limits(node.limits["unattended_idle_min"] * 60.0,
                             node.limits["unattended_max_hours"] * 3600.0)


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
        attendance.save_limits(store, limits_of(node))
        workers.save_host(store, node.name)  # the node dev mode is never for
        run(store, staging, stop, **node.retention)
    finally:
        store.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    _log.info("coordinator stopped")
    return 0
