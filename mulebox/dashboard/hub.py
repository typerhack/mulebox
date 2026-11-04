"""The dashboard's producers: one set of sampling loops shared by every viewer.

- queue: polls the store every QUEUE_S and publishes a `queue` event only when the
  status-model fingerprint changes (elapsed times tick in the browser).
- metrics: CPU, memory and own overhead every METRICS_S; Docker every DOCKER_S; disk
  every DISK_S. Each `metrics` event carries the newest value of every part; the last
  HISTORY samples are kept for the graphs of a viewer that just connected.

Sampling happens once no matter how many viewers there are. Blocking reads (SQLite,
/proc, statvfs) run in a worker thread so a slow disk never stalls the event loop.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from mulebox.common.log import get_logger
from mulebox.common.status import fingerprint, snapshot
from mulebox.dashboard import docker
from mulebox.dashboard.data import DashboardData
from mulebox.dashboard.events import EventBus
from mulebox.dashboard.metrics import Sampler, disk_usage

_log = get_logger(__name__)
QUEUE_S = 1.0
METRICS_S = 2.0
DOCKER_S = 5.0
DISK_S = 30.0
HISTORY = 150  # 5 minutes at METRICS_S


class Hub:
    def __init__(self, data: DashboardData, bus: EventBus, roots: dict[str, str], *,
                 sampler: Sampler | None = None,
                 docker_count: Callable[[], Awaitable[int | None]] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.data, self.bus, self.roots, self.clock = data, bus, roots, clock
        self.sampler = sampler or Sampler()
        socket = docker.socket_path()
        self.docker_count = docker_count or (lambda: docker.running_containers(socket))
        self.history: deque[dict[str, Any]] = deque(maxlen=HISTORY)
        self.disk: list[dict[str, Any]] = []
        self.docker: int | None = None
        self._queue_print: tuple | None = None
        self._tasks: list[asyncio.Task] = []

    # One step of each loop; the loops below only repeat them (tests call them directly).

    async def queue_step(self) -> bool:
        """Publish a `queue` event if the queue changed; True when one was published."""
        jobs = await asyncio.to_thread(self.data.queue_jobs)
        mark = fingerprint(jobs)
        if mark == self._queue_print:
            return False
        self._queue_print = mark
        self.bus.publish("queue", snapshot(jobs, self.clock()))
        return True

    async def metrics_step(self) -> dict[str, Any]:
        fast = await asyncio.to_thread(self.sampler.fast)
        sample = {"t": self.clock(), **fast, "disk": self.disk, "docker": self.docker,
                  "viewers": self.bus.subscriber_count}
        self.history.append(sample)
        self.bus.publish("metrics", sample)
        return sample

    async def docker_step(self) -> None:
        self.docker = await self.docker_count()

    async def disk_step(self) -> None:
        self.disk = await asyncio.to_thread(disk_usage, self.roots)

    def current_queue(self) -> dict[str, Any] | None:
        event = self.bus.latest.get("queue")
        return event.data if event else None

    # Lifecycle

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._every(QUEUE_S, self.queue_step), name="queue"),
            asyncio.create_task(self._every(DISK_S, self.disk_step), name="disk"),
            asyncio.create_task(self._every(DOCKER_S, self.docker_step), name="docker"),
            asyncio.create_task(self._every(METRICS_S, self.metrics_step), name="metrics"),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    @staticmethod
    async def _every(period: float, step: Callable[[], Awaitable[Any]]) -> None:
        while True:
            try:
                await step()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - one bad sample must not end the loop
                _log.exception("dashboard sampling failed")
            await asyncio.sleep(period)
