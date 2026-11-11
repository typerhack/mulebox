"""The dashboard's producers: one set of sampling loops shared by every viewer.

- queue: polls the store every QUEUE_S and publishes a `queue` event only when the
  status-model fingerprint changes (elapsed times tick in the browser).
- machines: reads the workers every MACHINES_S and publishes a `machines` event only when
  the panel changes, which includes a machine going quiet and, for the machine this
  dashboard runs on (`local_name`), its CPU and memory readings moving a whole percent.
  Other machines carry what their workers last reported (M5.3), and the same read feeds up to
  5 minutes of each worker's readings for its graphs (machine_history.py).
- metrics: CPU, memory, swap and own overhead every METRICS_S; Docker's containers and the
  memory of what runs for jobs every DOCKER_S; disk every DISK_S; Docker's disk use every
  DOCKER_DISK_S, as Docker sizes every image layer for it. Each `metrics` event carries the newest value of every part; the last
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
from mulebox.dashboard import docker, machines
from mulebox.dashboard.data import DashboardData
from mulebox.dashboard.events import EventBus
from mulebox.dashboard.machine_history import MachineHistory
from mulebox.dashboard.metrics import Sampler, disk_usage, jobs_memory

_log = get_logger(__name__)
QUEUE_S = 1.0
MACHINES_S = 2.0
METRICS_S = 2.0
DOCKER_S = 5.0
DISK_S = 30.0
DOCKER_DISK_S = 300.0
HISTORY = 150  # 5 minutes at METRICS_S


class Hub:
    def __init__(self, data: DashboardData, bus: EventBus, roots: dict[str, str], *,
                 sampler: Sampler | None = None,
                 docker_list: Callable[[], Awaitable[list[dict] | None]] | None = None,
                 docker_disk: Callable[[], Awaitable[int | None]] | None = None,
                 job_memory: Callable[[list[str], list[str]], int | None] = jobs_memory,
                 clock: Callable[[], float] = time.time, local_name: str | None = None) -> None:
        self.data, self.bus, self.roots, self.clock = data, bus, roots, clock
        # The worker on this machine; by default the one the data names.
        self.local_name = local_name if local_name is not None else getattr(data, "local_name", None)
        self.machine_history = MachineHistory()
        self.sampler = sampler or Sampler()
        socket = docker.socket_path()
        self.docker_list = docker_list or (lambda: docker.containers(socket))
        self.docker_disk = docker_disk or (lambda: docker.disk_use(socket))
        self.job_memory = job_memory
        self.history: deque[dict[str, Any]] = deque(maxlen=HISTORY)
        self.disk: list[dict[str, Any]] = []
        self.docker: int | None = None
        self.jobs_memory: int | None = None
        self.docker_bytes: int | None = None
        self._queue_print: tuple | None = None
        self._machines_print: tuple | None = None
        self._tasks: list[asyncio.Task] = []

    # One step of each loop; the loops below only repeat them (tests call them directly).

    async def queue_step(self) -> bool:
        """Publish a `queue` event if the queue changed; True when one was published."""
        jobs = await asyncio.to_thread(self.data.queue_jobs, self.clock())
        mark = fingerprint(jobs)
        if mark == self._queue_print:
            return False
        self._queue_print = mark
        self.bus.publish("queue", snapshot(jobs, self.clock()))
        return True

    async def machines_step(self) -> bool:
        """Publish a `machines` event if the panel changed; True when one was published."""
        now = self.clock()
        panel, found = await asyncio.to_thread(self.data.fleet, now)
        self.machine_history.record(found, now)
        machines.with_readings(panel, self.local_name, self.history[-1] if self.history else None)
        mark = machines.fingerprint(panel)
        if mark == self._machines_print:
            return False
        self._machines_print = mark
        self.bus.publish("machines", panel)
        return True

    async def metrics_step(self) -> dict[str, Any]:
        fast = await asyncio.to_thread(self.sampler.fast)
        sample = {"t": self.clock(), **fast, "disk": self.disk, "docker": self.docker,
                  "jobs_memory": self.jobs_memory, "docker_disk": self.docker_bytes,
                  "viewers": self.bus.subscriber_count}
        self.history.append(sample)
        self.bus.publish("metrics", sample)
        return sample

    async def docker_step(self) -> None:
        listing = await self.docker_list()
        self.docker = None if listing is None else len(listing)
        ids = docker.job_containers(listing or [], self.roots.get("runners"))
        queue = self.current_queue() or {}
        runners = [job["runner"] for job in queue.get("running", [])
                   if job.get("kind") == "runner" and job.get("runner")]
        self.jobs_memory = await asyncio.to_thread(self.job_memory, ids, runners)

    async def docker_disk_step(self) -> None:
        self.docker_bytes = await self.docker_disk()

    async def disk_step(self) -> None:
        self.disk = await asyncio.to_thread(disk_usage, self.roots)

    def current_queue(self) -> dict[str, Any] | None:
        event = self.bus.latest.get("queue")
        return event.data if event else None

    def current_machines(self) -> dict[str, Any] | None:
        event = self.bus.latest.get("machines")
        return event.data if event else None

    # Lifecycle

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._every(QUEUE_S, self.queue_step), name="queue"),
            asyncio.create_task(self._every(MACHINES_S, self.machines_step), name="machines"),
            asyncio.create_task(self._every(DISK_S, self.disk_step), name="disk"),
            asyncio.create_task(self._every(DOCKER_S, self.docker_step), name="docker"),
            asyncio.create_task(self._every(DOCKER_DISK_S, self.docker_disk_step), name="docker_disk"),
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
