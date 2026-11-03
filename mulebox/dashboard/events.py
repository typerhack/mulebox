"""The dashboard's event bus and Server-Sent Events encoding (docs/interfaces-m2.md).

One bus per server. Producers (hub.py) publish `queue` and `metrics` events; every
`/api/events` viewer subscribes. Bounded everywhere:

- The bus keeps the last KEEP events, so a viewer that reconnects with `Last-Event-ID`
  gets what it missed. An id from another server process (other epoch) or one older than
  the buffer gets a fresh snapshot instead (the caller decides; `since` returns None).
- Each subscriber has a queue of QUEUE_SIZE events. A viewer that falls that far behind
  is dropped (its stream ends) rather than slowing anyone else; its browser reconnects
  and resumes by event id.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections import deque
from dataclasses import dataclass
from typing import Any

KEEP = 256
QUEUE_SIZE = 64


@dataclass(frozen=True)
class Event:
    id: str
    type: str
    data: dict[str, Any]


def frame(type_: str, data: dict[str, Any], id_: str | None = None) -> bytes:
    """One SSE frame. Compact JSON never contains a raw line break."""
    text = json.dumps(data, separators=(",", ":"), allow_nan=False)
    head = f"id: {id_}\n" if id_ else ""
    return f"{head}event: {type_}\ndata: {text}\n\n".encode()


def encode(event: Event) -> bytes:
    return frame(event.type, event.data, event.id)


KEEPALIVE = b": keepalive\n\n"


class Subscriber:
    def __init__(self, size: int) -> None:
        self.queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=size)
        self.dropped = False

    def offer(self, event: Event) -> bool:
        """Queue `event`; False (and the subscriber is marked dropped) when full."""
        if self.dropped:
            return False
        try:
            self.queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            self.dropped = True
            return False


class EventBus:
    def __init__(self, keep: int = KEEP, queue_size: int = QUEUE_SIZE,
                 epoch: str | None = None) -> None:
        self.epoch = epoch or secrets.token_hex(4)
        self.queue_size = queue_size
        self._seq = 0
        self._recent: deque[Event] = deque(maxlen=keep)
        self._subscribers: set[Subscriber] = set()
        self.latest: dict[str, Event] = {}  # newest event of each type
        self.drops = 0

    def publish(self, type_: str, data: dict[str, Any]) -> Event:
        self._seq += 1
        event = Event(f"{self.epoch}-{self._seq}", type_, data)
        self._recent.append(event)
        self.latest[type_] = event
        for sub in list(self._subscribers):
            if not sub.offer(event):
                self.drops += 1
                self._subscribers.discard(sub)
                self._end(sub)
        return event

    def subscribe(self) -> Subscriber:
        sub = Subscriber(self.queue_size)
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subscribers.discard(sub)

    @property
    def last_id(self) -> str | None:
        """Id of the newest event, None before the first one."""
        return f"{self.epoch}-{self._seq}" if self._seq else None

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def since(self, last_id: str | None) -> list[Event] | None:
        """Events after `last_id`, or None when they cannot be replayed (send a snapshot)."""
        seq = self._parse(last_id)
        if seq is None or seq > self._seq:
            return None
        if seq == self._seq:
            return []
        oldest = self._parse(self._recent[0].id) if self._recent else None
        if oldest is None or seq + 1 < oldest:
            return None
        return [e for e in self._recent if self._parse(e.id) > seq]  # type: ignore[operator]

    def _parse(self, event_id: str | None) -> int | None:
        if not event_id or "-" not in event_id:
            return None
        epoch, _, number = event_id.rpartition("-")
        if epoch != self.epoch or not number.isdigit():
            return None
        return int(number)

    @staticmethod
    def _end(sub: Subscriber) -> None:
        """Wake a dropped subscriber's reader so its stream ends now."""
        while True:
            try:
                sub.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        sub.queue.put_nowait(None)
