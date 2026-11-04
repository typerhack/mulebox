"""`mulebox events`: a job's state changes as lines, for an agent or a tool to follow.

The lines come from the coordinator's `watch` stream, the one `check` follows, with the log
left out (`log: false`), through the shared status model (`common/status.py`, `job_event`).
A reconnect replays the current state, so an event is printed only when it differs from the
last one: nothing is repeated, and the final line cannot be lost, because a finished job
still answers a new `watch` with its result. An older coordinator sends the log anyway; it is
dropped here.

An event line is one JSON object with `v`, `event`, `job_id` and `state`. `event` is `queued`
(`position`, `waiting_for` when set), `started` (`machine`) or `finished` (`outcome`,
`exit_code`, `duration_s`). `exit_code` is the code the command exits with. Readers must
ignore events and keys they do not know: `stage` and `check_in` events are planned.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from mulebox.client import report
from mulebox.client.submit import RemoteLike, Streams, Watcher
from mulebox.common.protocol import Message, MessageType
from mulebox.common.status import job_event

Event = dict[str, Any]


def event_of(msg: Message) -> Event | None:
    """The event a stream message means, with the exit code a client reports."""
    if msg.type not in (MessageType.STATUS_OK, MessageType.RESULT):
        return None
    event = job_event(msg.body)
    if event is not None and event["event"] == "finished":
        event["exit_code"] = report.exit_code_for(msg.body)
    return event


def as_json(event: Event) -> str:
    return json.dumps(event, sort_keys=True, ensure_ascii=False)


def as_text(event: Event) -> str:
    """One readable line; `--json` has every key."""
    kind = event["event"]
    if kind == "queued":
        place = event.get("position")
        return f"queued, position {place}" if place is not None else "queued"
    if kind == "started":
        machine = event.get("machine")
        return f"started on {machine}" if machine else "started"
    return f"finished: {event.get('outcome')}, exit code {event.get('exit_code')}"


class EventStream(Watcher):
    """A Watcher that prints events instead of the log."""

    watch_options = {"log": False}

    def __init__(self, remote: RemoteLike, io: Streams, render: Callable[[Event], str]) -> None:
        super().__init__(remote, io)
        self.render = render
        self.last: Event | None = None

    def handle(self, msg: Message) -> bool:
        event = event_of(msg)
        if event is not None and event != self.last:
            self.last = event
            self.io.out.write(self.render(event) + "\n")
            self.io.out.flush()
        return msg.type is MessageType.RESULT
