"""Two ssh calls `common.ssh` does not offer: stdin from a file, and a two-way stream.

`run_remote` takes stdin as bytes (a 1 GiB snapshot would sit in memory) and
`stream_remote` closes stdin after its bytes (the watch stream must keep writing
heartbeats). Both helpers here build the command exactly as `common.ssh` does
(`ssh_base_argv` + `--` + `shlex.join(argv)`) and reuse its exit-code classification:
255 is SSHUnavailable, any other non-zero exit is RemoteError.

Children start in their own session, so a Ctrl-C reaches only mulebox, which then
cancels the job before it lets the connection go.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import IO

from mulebox.common import ssh

CLOSE_JOIN_S = 0.05  # a control master keeps stderr open; an agent is waiting for its result


def ssh_command(target: str, argv: Sequence[str], connect_timeout_s: int) -> list[str]:
    """The exact command `common.ssh` runs (validated the same way)."""
    return ssh.ssh_command(target, argv, connect_timeout_s)


def check_exit(target: str, argv: Sequence[str], code: int, stderr: bytes) -> None:
    """Raise the `common.ssh` error for a non-zero exit (255: SSHUnavailable)."""
    if code != 0:
        ssh.raise_for_exit(target, argv, code, stderr)


def run_with_file(
    target: str, argv: Sequence[str], source: Path, *, connect_timeout_s: int = 10
) -> ssh.RemoteResult:
    """Run argv on target with `source` streamed to its stdin; never reads it into memory.

    Raises SSHUnavailable on exit 255; any other exit code is returned (check it with
    `check_exit` after reading the reply on stdout).
    """
    command = ssh_command(target, argv, connect_timeout_s)
    with open(source, "rb") as stdin:
        try:
            proc = subprocess.run(
                command, stdin=stdin, capture_output=True, start_new_session=True
            )
        except OSError as exc:
            raise ssh.cannot_start(exc) from exc
    if proc.returncode == 255:
        check_exit(target, argv, 255, proc.stderr)
    return ssh.RemoteResult(proc.returncode, proc.stdout or b"", proc.stderr or b"")


class Duplex:
    """A running remote command with an open stdin (for writing) and stdout lines."""

    def __init__(self, target: str, argv: Sequence[str], *, connect_timeout_s: int = 10):
        self.target, self.argv = target, list(argv)
        command = ssh_command(target, argv, connect_timeout_s)
        try:
            self.proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            raise ssh.cannot_start(exc) from exc
        self._lock = threading.Lock()
        self._stderr = bytearray()
        self._drain = threading.Thread(target=ssh.drain_stream, args=(self.proc.stderr, self._stderr))
        self._drain.daemon = True
        self._drain.start()

    def write(self, data: bytes) -> bool:
        """Write to the remote stdin; False once the remote stopped reading."""
        with self._lock:
            try:
                assert self.proc.stdin is not None
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
                return True
            except (BrokenPipeError, OSError, ValueError):
                return False

    def readline(self, limit: int) -> bytes:
        assert self.proc.stdout is not None
        return self.proc.stdout.readline(limit)

    @property
    def stdout(self) -> IO[bytes]:
        assert self.proc.stdout is not None
        return self.proc.stdout

    def finish(self) -> None:
        """Close stdin, wait for the exit and raise the ssh error for a non-zero exit."""
        self.close_stdin()
        try:
            code = self.proc.wait(timeout=ssh.TERMINATE_GRACE_S)
        except subprocess.TimeoutExpired:
            self.close()
            return
        self._drain.join(timeout=ssh.THREAD_JOIN_S)
        check_exit(self.target, self.argv, code, bytes(self._stderr))

    def close_stdin(self) -> None:
        with self._lock:
            try:
                assert self.proc.stdin is not None
                self.proc.stdin.close()
            except OSError:
                pass

    def close(self) -> None:
        """Stop the process (if still running) and release every pipe; never raises."""
        self.close_stdin()
        ssh.reap(self.proc, [self._drain], join_s=CLOSE_JOIN_S)
