"""Up to five minutes of readings per worker, for the graphs of a machine the dashboard is not on
(`GET /api/metrics?machine=<name>`, metrics_api.py).

Fed by the machines loop (hub.py), which reads the workers every 2 s anyway: no extra read,
thread or request to the coordinator. A worker's readings are what it sent with its last claim or
heartbeat (`workers.load`, common/proc.py HostLoad); an entry is kept each time its `last_seen`
has moved on by MIN_GAP_S, which with the worker's own 2 s sampling is one entry per report it
measured anew. Bounded: entries older than WINDOW_S go, at most MAX_ENTRIES per worker, and a
worker no longer in the store is forgotten.

An entry is `{"t", "cpu": [per-core %], "memory": {"total","available","used"} | null,
"disk": [{"roots", "total", "used", "free"}]}`, the host's shape without `self`, `docker` and
`viewers`. A worker older than these readings gives `"cpu": []` and `"disk": []`.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from mulebox.coordinator.workers import is_online

WINDOW_S = 300.0
MIN_GAP_S = 1.5
MAX_ENTRIES = int(WINDOW_S / MIN_GAP_S)


def entry(worker: dict[str, Any]) -> dict[str, Any]:
    """One history entry from a stored worker row."""
    load = worker.get("load") or {}
    cpu, memory, disk = load.get("cpu"), load.get("memory"), load.get("disk")
    return {"t": worker["last_seen"], "cpu": list(cpu) if isinstance(cpu, list) else [],
            "memory": memory if isinstance(memory, dict) else None,
            "disk": [disk] if isinstance(disk, dict) else []}


class MachineHistory:
    def __init__(self) -> None:
        self._entries: dict[str, deque[dict[str, Any]]] = {}
        self._seen: dict[str, float] = {}

    def record(self, workers: list[dict[str, Any]], now: float) -> None:
        """Take the workers as the store has them now."""
        names = {worker["worker"] for worker in workers}
        for gone in set(self._entries) - names:
            del self._entries[gone], self._seen[gone]
        for worker in workers:
            name, seen = worker["worker"], worker["last_seen"]
            self._seen[name] = seen
            kept = self._entries.setdefault(name, deque(maxlen=MAX_ENTRIES))
            if is_online(worker, now) and (not kept or seen - kept[-1]["t"] >= MIN_GAP_S):
                kept.append(entry(worker))
            while kept and kept[0]["t"] < now - WINDOW_S:
                kept.popleft()

    def knows(self, name: str) -> bool:
        return name in self._seen

    def reply(self, name: str, now: float) -> dict[str, Any] | None:
        """The answer for worker `name`; None for a name it does not know. Offline: no history."""
        if name not in self._seen:
            return None
        seen = self._seen[name]
        online = is_online({"last_seen": seen}, now)
        kept = self._entries.get(name, ())
        return {"machine": name, "host": False, "last_seen": seen,
                "history": [item for item in kept if item["t"] >= now - WINDOW_S] if online else []}
