"""Wire protocol between client, coordinator and worker, and the job state machine.

Every message is one JSON object on one line (UTF-8, sorted keys, trailing newline):

    {"body": {...}, "request_id": "req-...", "type": "submit", "v": 1}

Envelope fields are exactly `v`, `type`, `request_id` and `body`. `request_id` is an
opaque non-empty string chosen by the sender; replies carry the same id. Body fields
listed in REQUIRED_FIELDS must be present; any other body field is optional and passed
through untouched. A peer speaking a different `v` is rejected with an upgrade hint.

See docs/interfaces.md (protocol.py) and docs/design.md (Job lifecycle, Connections).
"""

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from mulebox.common.errors import MuleboxError

PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 1 << 20  # 1 MiB per message line, newline included; readers enforce it


class ProtocolError(MuleboxError):
    """A message or state change that breaks the protocol."""


class JobState(StrEnum):
    UPLOADING = "uploading"
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    CLEANING = "cleaning"
    FINISHED = "finished"


class Outcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"


def _build_transitions() -> dict[JobState, frozenset[JobState]]:
    forward = {
        JobState.UPLOADING: JobState.QUEUED,
        JobState.QUEUED: JobState.STARTING,
        JobState.STARTING: JobState.RUNNING,
        JobState.RUNNING: JobState.CLEANING,
        JobState.CLEANING: JobState.FINISHED,
    }
    table = {}
    for state, nxt in forward.items():
        # Cancel and failure paths: any non-finished state may jump to cleaning or
        # finished. No state transitions to itself.
        table[state] = frozenset({nxt, JobState.CLEANING, JobState.FINISHED} - {state})
    table[JobState.FINISHED] = frozenset()
    return table


ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = _build_transitions()


def check_transition(old: JobState, new: JobState) -> None:
    """Raise ProtocolError unless a job may move from `old` to `new`."""
    for name, value in (("old", old), ("new", new)):
        if not isinstance(value, JobState):
            raise ProtocolError(f"{name} state must be a JobState, got {value!r}")
    if new not in ALLOWED_TRANSITIONS[old]:
        if old is JobState.FINISHED:
            raise ProtocolError(f"job is finished; cannot move to {new}")
        allowed = ", ".join(sorted(ALLOWED_TRANSITIONS[old]))
        raise ProtocolError(f"invalid job state transition {old} -> {new} (allowed: {allowed})")


class MessageType(StrEnum):
    SUBMIT = "submit"
    SUBMIT_OK = "submit_ok"
    UPLOAD_DONE = "upload_done"
    STATUS = "status"
    STATUS_OK = "status_ok"
    CANCEL = "cancel"
    HEARTBEAT = "heartbeat"
    CLAIM = "claim"
    CLAIM_OK = "claim_ok"
    CLAIM_NONE = "claim_none"
    JOB_UPDATE = "job_update"
    LOG_CHUNK = "log_chunk"
    RESULT = "result"
    ERROR = "error"
    QUEUE = "queue"
    QUEUE_OK = "queue_ok"
    PROJECTS = "projects"
    PROJECTS_OK = "projects_ok"
    MACHINES = "machines"
    MACHINES_OK = "machines_ok"
    LOGS = "logs"
    WATCH = "watch"
    RESERVE = "reserve"
    ACQUIRE = "acquire"
    RELEASE = "release"
    RUNNER_JOBS = "runner_jobs"


REQUIRED_FIELDS: dict[MessageType, frozenset[str]] = {
    # client -> coordinator: create (or, by idempotency_key, find) a job.
    MessageType.SUBMIT: frozenset(
        {"project", "job", "argv", "idempotency_key", "fingerprint", "base_commit", "client"}
    ),
    # coordinator -> client: the job exists; state is `uploading` (or later on a repeat).
    MessageType.SUBMIT_OK: frozenset({"job_id", "state"}),
    # client -> coordinator: snapshot upload complete; the job may be queued.
    MessageType.UPLOAD_DONE: frozenset({"job_id", "fingerprint"}),
    MessageType.STATUS: frozenset({"job_id"}),
    # `outcome` is added once the state is `finished`.
    MessageType.STATUS_OK: frozenset({"job_id", "state"}),
    MessageType.CANCEL: frozenset({"job_id"}),
    # client or worker -> coordinator: renew a lease (`lease` names which one).
    MessageType.HEARTBEAT: frozenset({"job_id", "lease"}),
    # worker -> coordinator: ask for the oldest job this worker can run.
    MessageType.CLAIM: frozenset({"worker", "capabilities", "free_slots"}),
    MessageType.CLAIM_OK: frozenset(
        {"job_id", "attempt_id", "project", "argv", "fingerprint", "base_commit", "timeout_min"}
    ),
    MessageType.CLAIM_NONE: frozenset(),
    # worker -> coordinator: the job moved to a new state.
    MessageType.JOB_UPDATE: frozenset({"job_id", "state"}),
    MessageType.LOG_CHUNK: frozenset({"job_id", "offset", "data"}),
    MessageType.RESULT: frozenset({"job_id", "outcome", "exit_code", "duration_s"}),
    # any side: a request failed. `code` is a short machine-readable word.
    MessageType.ERROR: frozenset({"code", "message"}),
    # client -> coordinator: list running, waiting and recent jobs.
    MessageType.QUEUE: frozenset(),
    MessageType.QUEUE_OK: frozenset({"jobs"}),
    MessageType.PROJECTS: frozenset(),
    MessageType.PROJECTS_OK: frozenset({"projects"}),
    # client -> coordinator: what the machines offer, for `mulebox doctor`.
    MessageType.MACHINES: frozenset(),
    MessageType.MACHINES_OK: frozenset({"version", "workers"}),
    # client -> coordinator: log bytes from `offset`; replied with one log_chunk.
    MessageType.LOGS: frozenset({"job_id", "offset"}),
    # client -> coordinator: stream log_chunk / status_ok until a final result.
    MessageType.WATCH: frozenset({"job_id", "offset"}),
    # runner hook -> coordinator: reserve a slot on `worker` for one GitHub Actions job;
    # replied with submit_ok (docs/interfaces-m3.md, Wire messages).
    MessageType.RESERVE: frozenset(
        {"worker", "repository", "job", "run_id", "run_attempt", "runner"}
    ),
    # runner hook -> coordinator: take the slot if it is free; replied with status_ok.
    MessageType.ACQUIRE: frozenset({"job_id"}),
    # runner hook or worker -> coordinator: end a reservation with `outcome`.
    MessageType.RELEASE: frozenset({"job_id", "outcome"}),
    # worker -> coordinator: unfinished reservations pinned to `worker`; replied queue_ok.
    MessageType.RUNNER_JOBS: frozenset({"worker"}),
}

# Body fields whose values are checked against an enum wherever they appear.
_ENUM_FIELDS: dict[str, type[StrEnum]] = {"state": JobState, "outcome": Outcome}
_ENVELOPE_FIELDS = frozenset({"v", "type", "request_id", "body"})


@dataclass(frozen=True)
class Message:
    type: MessageType
    request_id: str
    body: dict[str, Any] = field(default_factory=dict)
    v: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.type, MessageType):
            object.__setattr__(self, "type", _parse_type(self.type))
        _validate(self)


def _parse_type(value: object) -> MessageType:
    if not isinstance(value, str):
        raise ProtocolError(f"message field 'type' must be a string, got {type(value).__name__}")
    try:
        return MessageType(value)
    except ValueError:
        raise ProtocolError(f"unknown message type {value!r}") from None


def _check_version(v: object) -> None:
    if not isinstance(v, int) or isinstance(v, bool):
        raise ProtocolError(f"message field 'v' must be an integer, got {type(v).__name__}")
    if v != PROTOCOL_VERSION:
        side = "this side" if v > PROTOCOL_VERSION else "the other side"
        raise ProtocolError(
            f"protocol version mismatch: received v={v}, this mulebox speaks "
            f"v={PROTOCOL_VERSION}; upgrade mulebox on {side} so both sides match"
        )


def _validate(msg: Message) -> None:
    _check_version(msg.v)
    if not isinstance(msg.request_id, str) or not msg.request_id:
        raise ProtocolError("message field 'request_id' must be a non-empty string")
    if not isinstance(msg.body, dict):
        raise ProtocolError(f"message field 'body' must be an object, got {type(msg.body).__name__}")
    missing = REQUIRED_FIELDS[msg.type] - msg.body.keys()
    if missing:
        names = ", ".join(sorted(missing))
        raise ProtocolError(f"{msg.type} message is missing required body field(s): {names}")
    for name, enum in _ENUM_FIELDS.items():
        if name in msg.body:
            value = msg.body[name]
            if not isinstance(value, str) or value not in enum._value2member_map_:
                allowed = ", ".join(m.value for m in enum)
                raise ProtocolError(
                    f"{msg.type} body field '{name}' must be one of {allowed}; got {value!r}"
                )


def encode(msg: Message) -> bytes:
    """Serialize `msg` as one compact JSON line (sorted keys, UTF-8, trailing newline)."""
    _validate(msg)  # the body dict is mutable; re-check before sending
    envelope = {"v": msg.v, "type": msg.type.value, "request_id": msg.request_id, "body": msg.body}
    try:
        text = json.dumps(
            envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        data = text.encode("utf-8")
    except (TypeError, ValueError) as exc:  # UnicodeEncodeError is a ValueError
        raise ProtocolError(f"cannot encode {msg.type} message: {exc}") from None
    return data + b"\n"


def decode(line: bytes | str) -> Message:
    """Parse and validate one protocol line. Raises ProtocolError on any problem."""
    if isinstance(line, (bytes, bytearray)):
        try:
            line = bytes(line).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError(f"message is not valid UTF-8: {exc}") from None
    elif not isinstance(line, str):
        raise ProtocolError(f"message must be bytes or str, got {type(line).__name__}")
    if not line.strip():
        raise ProtocolError("empty message")
    if "\n" in line.rstrip("\r\n"):
        raise ProtocolError("message must be a single line")
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"message is not valid JSON: {exc}") from None
    except RecursionError:
        raise ProtocolError("message is not valid JSON: nested too deeply") from None
    if not isinstance(data, dict):
        raise ProtocolError(f"message must be a JSON object, got {type(data).__name__}")
    missing = _ENVELOPE_FIELDS - data.keys()
    if missing:
        raise ProtocolError(f"message is missing envelope field(s): {', '.join(sorted(missing))}")
    extra = data.keys() - _ENVELOPE_FIELDS
    if extra:
        raise ProtocolError(f"message has unknown envelope field(s): {', '.join(sorted(extra))}")
    # Version first: a newer peer may send types this side does not know yet.
    _check_version(data["v"])
    return Message(
        type=_parse_type(data["type"]),
        request_id=data["request_id"],
        body=data["body"],
        v=data["v"],
    )
