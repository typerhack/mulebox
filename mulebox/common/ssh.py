"""SSH transport: run a fixed remote executable on a build machine (docs/design.md).

Every call is `ssh -T -o BatchMode=yes -o ConnectTimeout=<n> <target> -- <command>`, run
with an argument list (never a local shell). The remote command is `shlex.join(argv)`, so
each argument reaches the remote program unchanged after the remote POSIX shell parses it.
Never build a remote command string any other way.

Exit code 255 from ssh means the connection failed (SSHUnavailable). Any other non-zero exit
is the remote command failing (RemoteError). A remote program that itself exits 255 is
indistinguishable from a connection failure; mulebox executables do not use that code.
"""

from __future__ import annotations

import shlex
import subprocess
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import IO

from mulebox.common.errors import MuleboxError

SSH_BINARY = "ssh"  # tests point this at a fake script
STDERR_KEEP_BYTES = 64 * 1024  # stderr kept by stream_remote (the last part)
MESSAGE_STDERR_CHARS = 500  # stderr shown in an error message (the last part)
TERMINATE_GRACE_S = 5.0  # wait after SIGTERM before SIGKILL
THREAD_JOIN_S = 2.0  # pipe threads are daemons; never wait on them forever


class SSHError(MuleboxError):
    """Base for SSH transport errors; raised directly for invalid targets or commands."""


class SSHUnavailable(SSHError):
    """The ssh connection failed (ssh exit 255) or ssh could not be started."""


class RemoteError(SSHError):
    """The remote command ran and exited non-zero."""

    def __init__(self, message: str, *, exit_code: int, stderr: bytes) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr


class RemoteTimeout(SSHError):
    """The local timeout expired; the ssh process was killed."""


@dataclass(frozen=True)
class RemoteResult:
    exit_code: int
    stdout: bytes
    stderr: bytes


def ssh_base_argv(target: str, connect_timeout_s: int = 10) -> list[str]:
    """Return the ssh argv up to and including the target (no remote command)."""
    _check_target(target)
    if isinstance(connect_timeout_s, bool) or not isinstance(connect_timeout_s, int):
        raise SSHError(f"connect timeout must be an integer, got {connect_timeout_s!r}")
    if connect_timeout_s < 1:
        raise SSHError(f"connect timeout must be at least 1 second, got {connect_timeout_s}")
    return [
        SSH_BINARY, "-T",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={connect_timeout_s}",
        target,
    ]


def run_remote(
    target: str,
    argv: Sequence[str],
    *,
    stdin: bytes | None = None,
    timeout_s: float | None = None,
    connect_timeout_s: int = 10,
    check: bool = True,
) -> RemoteResult:
    """Run argv on target and collect its output.

    Raises SSHUnavailable on a connection failure, RemoteTimeout when timeout_s expires,
    and RemoteError on another non-zero exit unless check is False (then the result is
    returned with its exit code).
    """
    command = ssh_command(target, argv, connect_timeout_s)
    io_kwargs: dict = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
    try:
        proc = subprocess.run(command, capture_output=True, timeout=timeout_s, **io_kwargs)
    except subprocess.TimeoutExpired as exc:
        raise RemoteTimeout(
            f"`{argv[0]}` on {target} did not finish within {timeout_s} s; "
            "the local ssh process was killed"
        ) from exc
    except OSError as exc:
        raise cannot_start(exc) from exc
    result = RemoteResult(proc.returncode, proc.stdout or b"", proc.stderr or b"")
    if result.exit_code == 255 or (check and result.exit_code != 0):
        raise_for_exit(target, argv, result.exit_code, result.stderr)
    return result


def stream_remote(
    target: str,
    argv: Sequence[str],
    *,
    stdin: bytes | None = None,
    connect_timeout_s: int = 10,
) -> Iterator[bytes]:
    """Yield stdout lines (with their newline) as they arrive; raise after a non-zero exit.

    Arguments are validated immediately; ssh starts on the first next(). stderr is drained
    on a thread so a chatty remote never blocks. The process is always reaped, also when the
    consumer stops early (close the iterator, or let it be garbage collected).
    """
    command = ssh_command(target, argv, connect_timeout_s)
    return _stream(command, target, list(argv), stdin)


def _stream(
    command: list[str], target: str, argv: list[str], stdin: bytes | None
) -> Iterator[bytes]:
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise cannot_start(exc) from exc
    stderr_buf = bytearray()
    threads = [_start_thread(drain_stream, proc.stderr, stderr_buf)]
    if stdin is not None:
        threads.append(_start_thread(_feed, proc.stdin, stdin))
    try:
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, b""):
            yield line
        proc.wait()
    finally:
        reap(proc, threads)
    if proc.returncode != 0:
        raise_for_exit(target, argv, proc.returncode, bytes(stderr_buf))


def ssh_command(target: str, argv: Sequence[str], connect_timeout_s: int) -> list[str]:
    if isinstance(argv, (str, bytes)):
        raise SSHError("remote argv must be a sequence of strings, not a single string")
    argv = list(argv)
    if not argv:
        raise SSHError("remote argv is empty; name the remote executable to run")
    if not all(isinstance(arg, str) for arg in argv):
        raise SSHError("remote argv must contain only strings")
    if any("\0" in arg for arg in argv):
        raise SSHError("remote argv must not contain NUL characters")
    # "--" ends ssh's option parsing, so the command can never be read as an ssh option.
    return ssh_base_argv(target, connect_timeout_s) + ["--", shlex.join(argv)]


def _check_target(target: str) -> None:
    if not isinstance(target, str) or not target:
        raise SSHError("ssh target is empty; set it to a host such as build-1")
    if target.startswith("-"):
        raise SSHError(f"ssh target {target!r} starts with '-' and would be read as an option")
    if any(ch.isspace() or ord(ch) < 32 or ch == "\x7f" for ch in target):
        raise SSHError(f"ssh target {target!r} contains whitespace or control characters")


def raise_for_exit(target: str, argv: Sequence[str], code: int, stderr: bytes) -> None:
    detail = _stderr_excerpt(stderr)
    suffix = f": {detail}" if detail else ""
    if code == 255:
        raise SSHUnavailable(
            f"cannot connect to {target} over ssh (exit 255){suffix}. "
            f"Check that `ssh {target}` works from this machine."
        )
    raise RemoteError(
        f"remote command `{argv[0]}` on {target} failed with exit code {code}{suffix}",
        exit_code=code,
        stderr=stderr,
    )


def _stderr_excerpt(stderr: bytes) -> str:
    text = stderr.decode("utf-8", errors="replace").strip()
    if len(text) > MESSAGE_STDERR_CHARS:
        text = "..." + text[-MESSAGE_STDERR_CHARS:]
    return text


def cannot_start(exc: OSError) -> SSHUnavailable:
    return SSHUnavailable(f"cannot start ssh ({SSH_BINARY!r}): {exc}. Is OpenSSH installed?")


def _start_thread(target, *args) -> threading.Thread:
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()
    return thread


def drain_stream(stream: IO[bytes], keep: bytearray) -> None:
    try:
        for chunk in iter(lambda: stream.read1(65536), b""):
            keep.extend(chunk)
            if len(keep) > STDERR_KEEP_BYTES:
                del keep[: len(keep) - STDERR_KEEP_BYTES]
    except (OSError, ValueError):
        pass  # pipe closed while reaping


def _feed(stream: IO[bytes], data: bytes) -> None:
    try:
        stream.write(data)
    except (BrokenPipeError, OSError, ValueError):
        pass  # the remote stopped reading; its exit code tells the story
    finally:
        try:
            stream.close()
        except OSError:
            pass


def reap(proc: subprocess.Popen, threads: list[threading.Thread]) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=TERMINATE_GRACE_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    for thread in threads:
        thread.join(timeout=THREAD_JOIN_S)
    for pipe in (proc.stdout, proc.stderr):
        if pipe is not None:
            try:
                pipe.close()
            except OSError:
                pass
