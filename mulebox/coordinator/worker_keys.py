"""Keys of workers on other machines, and what such a key may do (docs/install.md, More machines).

`mulebox setup <worker> --worker-of <coordinator>` makes a key on the worker and hands its public
half to `mulebox authorize-worker <name>` here. That writes one line into ~/.ssh/authorized_keys:

    command="<home>/.mulebox/bin/mulebox ssh-gate",restrict ssh-ed25519 AAAA... mulebox-worker:<name>

`restrict` turns off forwarding, a terminal and the like; `command=` means the key never gets a
shell: whatever it asks for, ssh runs `mulebox ssh-gate`, which reads the request from
SSH_ORIGINAL_COMMAND and allows only `mulebox rpc` and `mulebox rpc-download <job-id>`, and over
`rpc` only the requests a worker sends (WORKER_MESSAGES). Clients keep their own keys.

This is setup, not a job: it is the one file mulebox writes outside its roots, and it only ever
replaces the line that carries its own `mulebox-worker:<name>` marker.
"""

from __future__ import annotations

import os
import re
import shlex
import tempfile
from pathlib import Path

from mulebox.common.errors import MuleboxError
from mulebox.common.ids import is_valid_id
from mulebox.common.protocol import MessageType

MARKER = "mulebox-worker:"
WORKER_MESSAGES = frozenset({
    MessageType.CLAIM, MessageType.JOB_UPDATE, MessageType.LOG_CHUNK, MessageType.STEPS,
    MessageType.RESULT, MessageType.HEARTBEAT, MessageType.QUEUE, MessageType.RESERVE,
    MessageType.ACQUIRE, MessageType.RELEASE, MessageType.RUNNER_JOBS, MessageType.TAKEN,
    MessageType.UPGRADE,
})
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")
_KEY_TYPES = ("ssh-ed25519", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384",
              "ecdsa-sha2-nistp521", "ssh-rsa")
_BASE64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")


class GateRefused(MuleboxError):
    """A worker key asked for something it may not do."""


def gate_command(original: str | None) -> tuple[str, str | None]:
    """SSH_ORIGINAL_COMMAND -> ("rpc", None) or ("rpc-download", job_id); else GateRefused."""
    try:
        words = shlex.split(original or "")
    except ValueError as exc:
        raise GateRefused(f"cannot read the command: {exc}") from exc
    if not words or Path(words[0]).name != "mulebox":
        raise GateRefused("a worker key runs only mulebox")
    if words[1:] == ["rpc"]:
        return "rpc", None
    if len(words) == 3 and words[1] == "rpc-download" and is_valid_id(words[2], "job"):
        return "rpc-download", words[2]
    raise GateRefused("a worker key runs only `mulebox rpc` and `mulebox rpc-download <job>`")


def key_line(name: str, public_key: str, gate: str) -> str:
    if not _NAME.fullmatch(name):
        raise GateRefused(f"bad worker name {name!r}")
    parts = public_key.strip().split()
    if len(parts) < 2 or parts[0] not in _KEY_TYPES or not _BASE64.fullmatch(parts[1]) \
            or "\n" in public_key.strip():
        raise GateRefused("not one ssh public key line (ssh-ed25519 AAAA...)")
    return f'command="{gate} ssh-gate",restrict {parts[0]} {parts[1]} {MARKER}{name}'


def authorize(name: str, public_key: str, home: Path) -> Path:
    """Add the worker's key to `home`/.ssh/authorized_keys, replacing its earlier one."""
    line = key_line(name, public_key, str(home / ".mulebox" / "bin" / "mulebox"))
    folder = home / ".ssh"
    folder.mkdir(mode=0o700, exist_ok=True)
    path = folder / "authorized_keys"
    kept = [old for old in _lines(path) if not old.endswith(f" {MARKER}{name}")]
    _write(path, [*kept, line])
    return path


def _lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []


def _write(path: Path, lines: list[str]) -> None:
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".authorized_keys.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write("".join(f"{line}\n" for line in lines))
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def deauthorize(name: str, home: Path) -> bool:
    """Take the worker's key off; False if it had none here."""
    path = home / ".ssh" / "authorized_keys"
    lines = _lines(path)
    kept = [line for line in lines if not line.endswith(f" {MARKER}{name}")]
    if len(kept) == len(lines):
        return False
    _write(path, kept)
    return True
