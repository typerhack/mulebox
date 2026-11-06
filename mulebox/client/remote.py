"""The client's connection to the coordinator: `mulebox rpc` over ssh (interfaces-m1.md).

- `call(msg)`: one request line on stdin, one reply line on stdout.
- `upload(job_id, path, sha256)`: `rpc-upload <job_id> <sha256>` with the tar.gz streamed
  on stdin; the reply is `status_ok`.
- `watch(job_id, offset, lease, log)`: the request line, then a heartbeat line every 20 s on
  the still-open stdin; yields `log_chunk` / `status_ok` messages and finally the `result`.

An `error` reply raises CoordinatorError (its `code` kept); a reply that is not protocol
raises ProtocolError; connection failures raise `common.ssh.SSHUnavailable`.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from mulebox.client import sshio
from mulebox.common import ssh
from mulebox.common.config import ClientConfig
from mulebox.common.errors import MuleboxError
from mulebox.common.ids import new_id
from mulebox.common.protocol import (
    MAX_LINE_BYTES,
    Message,
    MessageType,
    ProtocolError,
    decode,
    encode,
)

HEARTBEAT_S = 20.0
CALL_TIMEOUT_S = 120.0
_READ_LIMIT = MAX_LINE_BYTES + 3  # one byte over the cap (plus CRLF) is enough to tell


class CoordinatorError(MuleboxError):
    """The coordinator answered with an `error` reply or broke the protocol."""

    def __init__(self, message: str, code: str = "protocol") -> None:
        super().__init__(message)
        self.code = code


class StreamEnded(CoordinatorError):
    """A watch stream stopped before its result; reconnecting gets the rest."""


def request(kind: MessageType, **body: Any) -> Message:
    return Message(kind, new_id("req"), body)


def remote_program(remote_bin: str) -> str:
    """`~/x` is sent as `x`: ssh starts in the home folder and shlex.join would quote `~`."""
    return remote_bin[2:] if remote_bin.startswith("~/") else remote_bin


class Remote:
    def __init__(self, config: ClientConfig, heartbeat_s: float = HEARTBEAT_S) -> None:
        self.target = config.coordinator
        self.program = remote_program(config.remote_bin)
        self.connect_timeout_s = config.connect_timeout_s
        self.heartbeat_s = heartbeat_s

    def call(self, msg: Message) -> Message:
        argv = [self.program, "rpc"]
        result = ssh.run_remote(
            self.target,
            argv,
            stdin=encode(msg),
            timeout_s=CALL_TIMEOUT_S,
            connect_timeout_s=self.connect_timeout_s,
            check=False,
        )
        return self._reply(argv, msg, result)

    def version(self) -> str:
        """`mulebox version` on the machine: the one question every mulebox can answer."""
        argv = [self.program, "version"]
        result = ssh.run_remote(self.target, argv, timeout_s=CALL_TIMEOUT_S,
                                connect_timeout_s=self.connect_timeout_s, check=False)
        sshio.check_exit(self.target, argv, result.exit_code, result.stderr)
        return result.stdout.decode("utf-8", errors="replace").strip()

    def upload(self, job_id: str, path: Path, sha256: str) -> Message:
        return self._send_file([self.program, "rpc-upload", job_id, sha256], path)

    def upload_plan(self, job_id: str, path: Path) -> Message:
        return self._send_file([self.program, "rpc-upload-plan", job_id], path)

    def upload_delta(self, job_id: str, path: Path, sha256: str, digest: str) -> Message:
        return self._send_file([self.program, "rpc-upload-delta", job_id, sha256, digest], path)

    def _send_file(self, argv: list[str], path: Path) -> Message:
        result = sshio.run_with_file(
            self.target, argv, path, connect_timeout_s=self.connect_timeout_s
        )
        return self._reply(argv, None, result)

    def watch(self, job_id: str, offset: int = 0, lease: bool = True,
              log: bool = True) -> Iterator[Message]:
        options = {} if log else {"log": False}
        msg = request(MessageType.WATCH, job_id=job_id, offset=offset, lease=lease, **options)
        return self._watch(msg, job_id)

    def _watch(self, msg: Message, job_id: str) -> Iterator[Message]:
        stream = sshio.Duplex(
            self.target, [self.program, "rpc"], connect_timeout_s=self.connect_timeout_s
        )
        stop = threading.Event()
        beats = threading.Thread(target=self._beat, args=(stream, job_id, stop), daemon=True)
        try:
            stream.write(encode(msg))
            beats.start()
            while True:
                line = stream.readline(_READ_LIMIT)
                if not line or (len(line) < _READ_LIMIT and not line.endswith(b"\n")):
                    break  # the end, or half a line from a connection that dropped
                reply = _decode_line(line)
                yield reply
                if reply.type is MessageType.RESULT:
                    return
            stop.set()
            stream.finish()  # raises SSHUnavailable / RemoteError for a failed exit
            raise StreamEnded(f"the watch stream for {job_id} ended without a result")
        finally:
            stop.set()
            stream.close()

    def _beat(self, stream: sshio.Duplex, job_id: str, stop: threading.Event) -> None:
        while not stop.wait(self.heartbeat_s):
            line = encode(request(MessageType.HEARTBEAT, job_id=job_id, lease="client"))
            if not stream.write(line):
                return

    def _reply(self, argv: list[str], msg: Message | None, result: ssh.RemoteResult) -> Message:
        reply = read_reply(result.stdout, msg)
        if reply is None:
            sshio.check_exit(self.target, argv, result.exit_code, result.stderr)
            raise CoordinatorError(f"`{argv[1]}` on {self.target} gave no reply")
        return reply


def read_reply(stdout: bytes, msg: Message | None) -> Message | None:
    """The reply in the output of `mulebox rpc`, None when it wrote none. Raises like `call`."""
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    if not lines:
        return None
    reply = _decode_line(lines[0])
    if msg is not None and reply.request_id != msg.request_id:
        raise CoordinatorError(
            f"reply to {msg.type} has request id {reply.request_id!r}, "
            f"expected {msg.request_id!r}"
        )
    return reply


def _decode_line(line: bytes) -> Message:
    if len(line) > MAX_LINE_BYTES + 2:  # + line break
        raise CoordinatorError("the coordinator sent a line over the 1 MiB protocol limit")
    try:
        reply = decode(line)
    except ProtocolError as exc:
        raise CoordinatorError(f"bad reply from the coordinator: {exc}") from exc
    if reply.type is MessageType.ERROR:
        code = str(reply.body.get("code", "internal"))
        raise CoordinatorError(f"coordinator: {reply.body.get('message', '')} ({code})", code)
    return reply
