"""How the worker talks to the coordinator (docs/interfaces-m1.md, Worker).

- `LocalLink`: coordinator on the same machine; calls `coordinator.api.handle` directly.
  This is the only import from the worker into the coordinator package, done lazily so
  the worker can be imported (and tested) without it.
- `SSHLink`: coordinator on another machine; runs `mulebox rpc` there over ssh.

Transport failures (coordinator unreachable, store locked, broken reply) raise
`LinkError`, which the agent counts as "coordinator unreachable". An `error` reply is
not a transport failure and is returned as a message.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Protocol

from mulebox.common import protocol
from mulebox.common.errors import MuleboxError
from mulebox.common.ids import new_id
from mulebox.common.protocol import Message, MessageType
from mulebox.common.ssh import RemoteError, SSHError, run_remote

RPC_TIMEOUT_S = 60.0
DOWNLOAD_TIMEOUT_S = 1800.0


class LinkError(MuleboxError):
    """The coordinator could not be reached or gave no usable reply."""


class CoordinatorLink(Protocol):
    def call(self, msg: Message) -> Message: ...
    def fetch_snapshot(self, job_id: str, dest: Path) -> None: ...


def request(kind: MessageType, **body: Any) -> Message:
    """A new request message with a fresh `req-` id."""
    return Message(type=kind, request_id=new_id("req"), body=body)


def remote_command(remote_bin: str) -> str:
    """`~/x` -> `x`: ssh starts in the home folder, and shlex.join would quote `~`."""
    return remote_bin[2:] if remote_bin.startswith("~/") else remote_bin


class LocalLink:
    def __init__(self, store: Any, staging: Any) -> None:
        self.store = store
        self.staging = staging

    def call(self, msg: Message) -> Message:
        from mulebox.coordinator import api  # lazy: see the module docstring

        try:
            return api.handle(self.store, self.staging, msg, time.time())
        except MuleboxError as exc:
            raise LinkError(f"coordinator request {msg.type} failed: {exc}") from exc
        except Exception as exc:  # sqlite3 errors (locked, disk) and the like
            raise LinkError(f"coordinator request {msg.type} failed: {exc!r}") from exc

    def fetch_snapshot(self, job_id: str, dest: Path) -> None:
        try:
            self.staging.download(job_id, dest)
        except Exception as exc:
            raise LinkError(f"cannot read the snapshot of {job_id}: {exc}") from exc


class SSHLink:
    def __init__(self, target: str, remote_bin: str, connect_timeout_s: int = 10) -> None:
        self.target = target
        self.remote_bin = remote_command(remote_bin)
        self.connect_timeout_s = connect_timeout_s

    def _run(self, args: list[str], stdin: bytes | None, timeout_s: float) -> bytes:
        try:
            result = run_remote(self.target, [self.remote_bin, *args], stdin=stdin,
                                timeout_s=timeout_s, connect_timeout_s=self.connect_timeout_s)
        except RemoteError as exc:
            raise LinkError(f"`mulebox {args[0]}` on {self.target} failed: {exc}") from exc
        except SSHError as exc:
            raise LinkError(str(exc)) from exc
        return result.stdout

    def call(self, msg: Message) -> Message:
        out = self._run(["rpc"], protocol.encode(msg), RPC_TIMEOUT_S)
        line = out.split(b"\n", 1)[0]
        if len(line) > protocol_line_cap():
            raise LinkError("coordinator reply exceeds the line cap")
        try:
            return protocol.decode(line)
        except protocol.ProtocolError as exc:
            raise LinkError(f"bad reply from the coordinator: {exc}") from exc

    def fetch_snapshot(self, job_id: str, dest: Path) -> None:
        data = self._run(["rpc-download", job_id], None, DOWNLOAD_TIMEOUT_S)
        with open(dest, "xb") as fh:
            fh.write(data)


def protocol_line_cap() -> int:
    """`MAX_LINE_BYTES` from protocol.py once it exists there; 1 MiB per the contract."""
    return getattr(protocol, "MAX_LINE_BYTES", 1024 * 1024)

