"""`mulebox events`: a job's state changes as lines, for an agent or a tool to follow.

The lines come from the coordinator's `watch` stream, the one `check` follows, with the log
left out (`log: false`), through the shared status model (`common/status.py`, `job_event`).
A reconnect replays the current state, so an event is printed only when it differs from the
last one: nothing is repeated, and the final line cannot be lost, because a finished job
still answers a new `watch` with its result. An older coordinator sends the log anyway; it is
dropped here.

An event line is one JSON object with `v`, `event`, `job_id` and `state`. `event` is `queued`
(`position`, `waiting_for` when set, `running_ahead`: the jobs on the machines now), `started` (`machine`) or `finished` (`outcome`,
`exit_code`, `duration_s`, `stage`: where a job that ended badly failed, null when that is not
known, and `stop_reason` for outcome `stopped`), `check_in` (`number`, `elapsed_s`, `stage`,
`output_idle_s`, `last_line`, `idle_s`, `job_cpu_pct`, `cpu_pct`, `net_kib_s`; every
`timeout_min`, readings null when the worker could not measure them).
`taken_back`: seen once, by the watcher that takes the job back) or `stage` (`stage`, `number`,
`started_at`: the job entered a stage; someone who connects late gets the current one).
`exit_code` is the code the command exits with. Readers must ignore events and keys they do not
know.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from mulebox.client import attention, report
from mulebox.client.submit import RemoteLike, Streams, Watcher
from mulebox.common.protocol import Message, MessageType
from mulebox.common.status import NOTICES, job_event

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
    if kind == "check_in":
        return attention.check_in_line(str(event.get("job_id")), event)
    if kind == "stage":
        return f"stage {event.get('stage')}"
    if kind == "queued":
        place = event.get("position")
        line = f"queued, position {place}" if place is not None else "queued"
        ahead = event.get("running_ahead")
        return f"{line}, behind {', '.join(ahead)}" if ahead else line
    if kind == "started":
        machine = event.get("machine")
        return f"started on {machine}" if machine else "started"
    stage = event.get("stage")
    where = f", failed stage {stage}" if stage else ""
    return f"finished: {event.get('outcome')}, exit code {event.get('exit_code')}{where}"


class EventStream(Watcher):
    """A Watcher that prints events instead of the log."""

    watch_options = {"log": False}

    def __init__(self, remote: RemoteLike, io: Streams, render: Callable[[Event], str]) -> None:
        super().__init__(remote, io)
        self.render = render
        self.last: Event | None = None
        self.notices: set[tuple] = set()

    def _is_new(self, event: Event) -> bool:
        """State events differ from the last one, notices from every one before."""
        if event["event"] in NOTICES:
            key = (event["event"], event.get("number"), event.get("since"))
            new, _ = key not in self.notices, self.notices.add(key)
            return new
        new, self.last = event != self.last, event
        return new

    def handle(self, msg: Message) -> bool:
        event = event_of(msg)
        if event is not None and self._is_new(event):
            self.io.out.write(self.render(event) + "\n")
            self.io.out.flush()
        return msg.type is MessageType.RESULT
