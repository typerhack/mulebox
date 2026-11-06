"""Entry points `mulebox rpc`, `rpc-upload` and `rpc-download` (stdin/stdout).

- `rpc`: reads exactly one request line (cap MAX_LINE_BYTES) and writes one reply line;
  `watch` streams instead (watch.py).
- `rpc-upload <job_id> <sha256>`: tar.gz bytes on stdin, one reply line on stdout.
- `rpc-upload-plan <job_id>`: a file list on stdin, one reply line saying what to send.
- `rpc-upload-delta <job_id> <sha256> <digest>`: tar.gz of those files on stdin, one reply line.
- `rpc-download <job_id>`: tar.gz bytes on stdout; errors only on stderr.

Nothing here ever prints a traceback on stdout: every failure becomes an `error` reply.
Exit codes: 0 when the reply is not an error; 4 (protocol/remote error) when it is, and
the error is repeated on stderr for callers that only see stderr.
"""

import time
from collections.abc import Callable
from typing import Any, BinaryIO, TextIO

from mulebox.common.ids import new_id
from mulebox.common.log import get_logger
from mulebox.common.protocol import Message, MessageType, ProtocolError, decode
from mulebox.coordinator import api, delta, uploads
from mulebox.coordinator.context import error_message
from mulebox.coordinator.errors import BadRequest, CoordinatorError
from mulebox.coordinator.lineio import note_error, read_line, write_message
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store
from mulebox.coordinator.views import status_body
from mulebox.coordinator.watch import POLL_S, watch

_log = get_logger(__name__)
EXIT_OK = 0
EXIT_PROTOCOL = 4


def run_rpc(store: Store, staging: Staging, stdin: BinaryIO, stdout: BinaryIO,
            stderr: TextIO | None = None, *, clock: Callable[[], float] = time.time,
            sleep: Callable[[float], None] = time.sleep, poll_s: float = POLL_S,
            cluster_slots: int = 1, dashboard: dict[str, Any] | None = None) -> int:
    """Answer one request from `stdin` on `stdout`; return the exit code."""
    request_id = "unknown"
    try:
        line = read_line(stdin)
        if line is None:
            raise BadRequest("no request line on stdin")
        msg = decode(line)
        request_id = msg.request_id
        if msg.type is MessageType.WATCH:
            return watch(store, staging, msg, stdin, stdout, clock=clock, sleep=sleep,
                         poll_s=poll_s)
        reply = api.handle(store, staging, msg, clock(), cluster_slots=cluster_slots,
                           dashboard=dashboard)
    except CoordinatorError as exc:
        reply = error_message(request_id, exc.code, str(exc))
    except ProtocolError as exc:
        reply = error_message(request_id, "bad_request", str(exc))
    except (BrokenPipeError, ConnectionResetError):
        return EXIT_PROTOCOL  # the caller went away mid-stream; nobody to tell
    except Exception as exc:  # noqa: BLE001
        _log.exception("internal error in rpc")
        reply = error_message(request_id, "internal", f"internal error: {type(exc).__name__}")
    return _send_reply(stdout, stderr, reply)


def run_upload(store: Store, staging: Staging, job_id: str, sha256: str, stdin: BinaryIO,
               stdout: BinaryIO, stderr: TextIO | None = None, *,
               clock: Callable[[], float] = time.time) -> int:
    """Receive a snapshot for `job_id`; reply status_ok (state `queued`) or error."""
    def receive() -> dict[str, Any]:
        return status_body(*uploads.accept_upload(store, staging, job_id, sha256, stdin, clock()))
    return _answer(receive, "rpc-upload", stdout, stderr)


def run_upload_plan(store: Store, staging: Staging, job_id: str, stdin: BinaryIO,
                    stdout: BinaryIO, stderr: TextIO | None = None) -> int:
    """Read the client's file list; reply which files it has to send."""
    return _answer(lambda: delta.plan(store, staging, job_id, stdin),
                   "rpc-upload-plan", stdout, stderr, MessageType.UPLOAD_PLAN_OK)


def run_upload_delta(store: Store, staging: Staging, job_id: str, sha256: str, digest: str,
                     stdin: BinaryIO, stdout: BinaryIO, stderr: TextIO | None = None, *,
                     clock: Callable[[], float] = time.time) -> int:
    """Receive the changed files for `job_id`; reply as `run_upload` does."""
    def receive() -> dict[str, Any]:
        return status_body(*delta.accept(store, staging, job_id, sha256, digest, stdin, clock()))
    return _answer(receive, "rpc-upload-delta", stdout, stderr)


def _answer(work: Callable[[], dict[str, Any]], name: str, stdout: BinaryIO,
            stderr: TextIO | None, kind: MessageType = MessageType.STATUS_OK) -> int:
    request_id = new_id("req")
    try:
        reply = Message(kind, request_id, work())
    except CoordinatorError as exc:
        reply = error_message(request_id, exc.code, str(exc))
    except Exception as exc:  # noqa: BLE001
        _log.exception("internal error in %s", name)
        reply = error_message(request_id, "internal", f"internal error: {type(exc).__name__}")
    return _send_reply(stdout, stderr, reply)


def run_download(store: Store, staging: Staging, job_id: str, stdout: BinaryIO,
                 stderr: TextIO | None = None) -> int:
    """Write the snapshot of `job_id` to `stdout`; on failure only stderr and exit 4."""
    try:
        uploads.send_snapshot(store, staging, job_id, stdout)
        stdout.flush()
        return EXIT_OK
    except CoordinatorError as exc:
        reply = error_message("download", exc.code, str(exc))
    except (BrokenPipeError, ConnectionResetError):
        return EXIT_PROTOCOL
    except Exception as exc:  # noqa: BLE001
        _log.exception("internal error in rpc-download")
        reply = error_message("download", "internal", f"internal error: {type(exc).__name__}")
    note_error(stderr, reply)
    return EXIT_PROTOCOL


def _send_reply(stdout: BinaryIO, stderr: TextIO | None, reply: Message) -> int:
    try:
        write_message(stdout, reply)
    except (BrokenPipeError, ConnectionResetError):
        return EXIT_PROTOCOL
    note_error(stderr, reply)
    return EXIT_PROTOCOL if reply.type is MessageType.ERROR else EXIT_OK
