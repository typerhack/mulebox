"""The worker's threads for its isolated runners (place.py): one per place folder.

`sync` runs with the worker's loop: it starts a thread for a place folder that has none (added
by `mulebox runner add --isolated`, or found at the worker's start) and stops the thread of a
folder that is gone or no longer isolated. `shutdown` stops them all and waits a little: each
removes its container and releases its slot, as a worker that stops ends its jobs.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.common.log import get_logger
from mulebox.runners import guard, layout
from mulebox.runners.place import Place
from mulebox.worker.link import CoordinatorLink
from mulebox.worker.paths import NodePaths

LOG = get_logger("runners.places")
SYNC_S = 10.0
STOP_WAIT_S = 90.0


def place_folders(paths: NodePaths) -> list[Path]:
    """Runner folders whose metadata says isolated, and not being removed."""
    found = []
    for folder in layout.runner_folders(paths):
        meta = guard.runner_meta(folder) or {}
        if meta.get("isolated") is True and not meta.get("removing"):
            found.append(folder)
    return found


class PlaceKeeper:
    def __init__(self, worker: str, link: CoordinatorLink, paths: NodePaths, *,
                 make: Callable[..., Any] = Place, clock: Callable[[], float] = time.monotonic):
        self.worker, self.link, self.paths = worker, link, paths
        self.make, self.clock = make, clock
        self.running: dict[str, tuple[threading.Thread, threading.Event]] = {}
        self.stopping: dict[str, threading.Thread] = {}  # told to stop, not ended yet
        self.next_at = 0.0

    def sync(self) -> None:
        now = self.clock()
        if now < self.next_at:
            return
        self.next_at = now + SYNC_S
        wanted = {f.name: f for f in place_folders(self.paths)}
        for name in [n for n in self.running if n not in wanted]:
            self._stop(name)
        self.stopping = {n: t for n, t in self.stopping.items() if t.is_alive()}
        for name, folder in wanted.items():
            thread = self.running.get(name)
            if (thread is None or not thread[0].is_alive()) and name not in self.stopping:
                self._start(name, folder)

    def _start(self, name: str, folder: Path) -> None:
        stop = threading.Event()
        place = self.make(folder, self.worker, self.link, self.paths, stop=stop)
        thread = threading.Thread(target=place.run, name=f"place-{name}", daemon=True)
        thread.start()
        self.running[name] = (thread, stop)
        LOG.info("isolated runner %s started", name)

    def _stop(self, name: str) -> None:
        """Tell its thread to stop, without waiting: the worker loop goes on meanwhile."""
        thread, stop = self.running.pop(name)
        stop.set()
        self.stopping[name] = thread
        LOG.info("isolated runner %s stopping", name)

    def shutdown(self) -> None:
        for name in list(self.running):
            self._stop(name)
        deadline = self.clock() + STOP_WAIT_S
        for thread in self.stopping.values():
            thread.join(timeout=max(0.0, deadline - self.clock()))
        self.stopping.clear()
