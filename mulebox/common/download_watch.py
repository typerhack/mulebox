"""A running job's download, as its card and `mulebox status` show it (docs/design.md, Downloads).

Fed with the job's output lines (common/download_lines.py) and their times, image bytes from
worker/pullnoise.py, the step or stage the job is in, and at each heartbeat its CPU and, where it
is measured, its network traffic. `reading` gives one dict, or None when nothing is downloading:

- `what` (`cache`, `tool`, `package`, `browser`, `image`, or `network` for the job's own traffic
  with no line to name it), `name` and `step`;
- `done_bytes` and `total_bytes` as the tool printed them (null when it printed none), and
  `rate_bytes_s` from those figures over the last minute or so; `as_of_s` is how old they are,
  as a GitHub runner writes a step's output to the node in blocks of about 4 KB, so on a slow
  line the figures can trail by minutes;
- `net_bytes_s` and `net_scope`: the traffic measured now, `job` when it is the job's own (an
  isolated runner's container), `machine` when it is the whole node's, which a VPN and a desktop
  keep busy, so it never decides anything here;
- `waiting_on_network`: the job's CPU is under a tenth of a core, so the wait is the network;
- `quiet_s` and `stalled`: how long no byte moved, and whether that is STALL_S or more. From the
  job's own traffic when it is measured, else from the printed figures; null when neither is
  known, as for pip, which names a file and its size and nothing after.

A download belongs to its step: a new step forgets it. One that reached its total has ended.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from mulebox.common import download_lines as dl
from mulebox.common.status import number

STALL_S = 60.0
RATE_WINDOW_S = 60.0
IDLE_CPU_PCT = 10.0  # coordinator/attendance.py and web/src/lib/quiet.ts draw the same line
MOVING_BYTES_S = 4 * 1024.0  # the job's own traffic above this moves bytes (job_meter.py's line)
NETWORK_BYTES_S = 16 * 1024.0  # above this, with no line and an idle CPU, it is a download
KEYS = ("what", "name", "step", "done_bytes", "total_bytes", "rate_bytes_s", "as_of_s",
        "net_bytes_s", "net_scope", "waiting_on_network", "quiet_s", "stalled")
SCOPES = ("job", "machine")
MAX_TEXT = 200
MAX_POINTS = 512  # a busy pnpm prints many lines a second


class _Item:
    def __init__(self, what: str, name: str | None, at: float) -> None:
        self.what, self.name = what, name
        self.done: int | None = None
        self.total: int | None = None
        self.seen_at = self.started_at = at
        self.moved_at: float | None = None
        self.points: deque[tuple[float, int]] = deque(maxlen=MAX_POINTS)

    def progress(self, done: int | None, total: int | None, at: float) -> None:
        self.seen_at = max(self.seen_at, at)
        if total:
            self.total = total
        if done is None:
            return
        if done > (self.done or 0):
            self.moved_at = at
        self.done = max(done, self.done or 0)
        self.points.append((at, self.done))
        while len(self.points) > 2 and self.points[1][0] <= at - RATE_WINDOW_S:  # one stays before
            self.points.popleft()

    @property
    def finished(self) -> bool:
        return self.done is not None and self.total is not None and self.done >= self.total

    def rate(self) -> float | None:
        if len(self.points) < 2 or self.points[-1][0] <= self.points[0][0]:
            return None
        (t0, d0), (t1, d1) = self.points[0], self.points[-1]
        return round((d1 - d0) / (t1 - t0), 1)


class DownloadWatch:
    """`live`: lines arrive as they are printed (an agent job's log). A GitHub runner's trail
    (live=False), so there only the span its figures cover counts as quiet, not the time since."""

    def __init__(self, live: bool = True) -> None:
        self.live = live
        self._item: _Item | None = None
        self._step: str | None = None
        self._traffic_since: float | None = None  # first reading of the job's own traffic
        self._traffic_moved_at: float | None = None

    def step(self, name: str | None) -> None:
        """The job is in a new step or stage: what it was downloading is over."""
        if name != self._step:
            self._step, self._item = name, None
            self._traffic_since = self._traffic_moved_at = None

    def line(self, text: str, at: float) -> None:
        seen = dl.parse(text)
        if seen is None:
            return
        item = self._item
        same = item is not None and item.what == seen.what
        if seen.kind == dl.END:
            if same:
                self._item = None
            return
        if seen.kind == dl.START or item is None or not same or \
                (seen.name and item.name and seen.name != item.name):
            item = self._item = _Item(seen.what, seen.name, at)
        elif seen.name and not item.name:
            item.name = seen.name
        item.progress(seen.done, seen.total, at)
        if item.finished:
            self._item = None

    def image_bytes(self, done: int, total: int | None, at: float) -> None:
        """Image layers so far (pullnoise.py), and their size when every layer gave one."""
        if self._item is None or self._item.what != dl.IMAGE:
            self._item = _Item(dl.IMAGE, None, at)
        self._item.progress(done, total, at)

    def _own_quiet(self, now: float, net_bytes_s: float) -> float:
        """Seconds the job's own traffic has stayed under MOVING_BYTES_S."""
        if self._traffic_since is None:
            self._traffic_since = now
        if net_bytes_s >= MOVING_BYTES_S:
            self._traffic_moved_at = now
        return now - (self._traffic_moved_at or self._traffic_since)

    def _figures_quiet(self, item: _Item, now: float) -> float | None:
        if item.done is None:
            return None
        moved = item.moved_at if item.moved_at is not None else item.started_at
        return (now if self.live else item.seen_at) - moved

    def reading(self, now: float, cpu_pct: float | None = None, net_bytes_s: float | None = None,
                net_scope: str | None = None) -> dict[str, Any] | None:
        own = net_scope == "job" and net_bytes_s is not None
        quiet = self._own_quiet(now, net_bytes_s) if own else None
        idle = None if cpu_pct is None else cpu_pct < IDLE_CPU_PCT
        item = self._item
        if item is None:
            if not (own and net_bytes_s >= NETWORK_BYTES_S and idle):
                return None  # nothing named, and no traffic of its own while it waits
            item = _Item(dl.NETWORK, None, now)
        if quiet is None:
            quiet = self._figures_quiet(item, now)
        quiet = None if quiet is None else round(max(0.0, quiet), 1)
        return {"what": item.what, "name": item.name, "step": self._step,
                "done_bytes": item.done, "total_bytes": item.total, "rate_bytes_s": item.rate(),
                "as_of_s": round(max(0.0, now - item.seen_at), 1) if item.done is not None else None,
                "net_bytes_s": None if net_bytes_s is None else round(net_bytes_s, 1),
                "net_scope": net_scope if net_bytes_s is not None else None,
                "waiting_on_network": idle, "quiet_s": quiet,
                "stalled": None if quiet is None else quiet >= STALL_S}


def clean(value: Any) -> dict[str, Any] | None:
    """A reading off the wire with only its known keys and types, None when it is not one."""
    if not isinstance(value, dict) or not isinstance(value.get("what"), str):
        return None
    out: dict[str, Any] = {}
    for key in KEYS:
        item = value.get(key)
        if key in ("what", "name", "step"):
            out[key] = item[:MAX_TEXT] if isinstance(item, str) else None
        elif key == "net_scope":
            out[key] = item if item in SCOPES else None
        elif key in ("waiting_on_network", "stalled"):
            out[key] = item if isinstance(item, bool) else None
        else:
            found = number(item)
            out[key] = int(found) if found is not None and key.endswith("_bytes") else found
    return out
