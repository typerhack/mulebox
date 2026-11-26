"""The one place the worker runs the docker CLI.

No shell is involved. Every call has a timeout, so a hung daemon cannot stop the worker
for good, and errors carry redacted text, because compose output can quote env values.
`prune` and `system` are refused here whatever the caller asks: a job's cleanup removes only
what it found by exact job label (docker_cleanup.py). The exceptions are exact forms only:
`system df`, which reads, and the storage cleanup's prunes of build cache and dangling images
unused for a number of hours (docker_prune.py), never volumes, networks, containers, tagged
images or `system prune`. The
runner is injected, and tests use a fake one: they never touch a real Docker daemon.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from mulebox.common.errors import MuleboxError
from mulebox.common.redact import Redactor

CALL_TIMEOUT_S = 60.0
_REFUSED = frozenset({"prune", "system"})
_READ_ONLY = (("system", "df"),)  # the one `system` call allowed: it only reads totals
_PRUNES = (("builder", "prune", "--force"), ("image", "prune", "--force"))  # dangling only
# each then `--filter until=<hours>h` and nothing else; `image prune --all` is never allowed
_UNTIL = re.compile(r"^until=[1-9][0-9]{0,5}h$")


def allowed_prune(args: Sequence[str]) -> bool:
    """True for exactly one of the storage cleanup's prune forms (docker_prune.py)."""
    head, tail = tuple(args[:-2]), tuple(args[-2:])
    return (head in _PRUNES and len(tail) == 2 and tail[0] == "--filter"
            and bool(_UNTIL.match(tail[1])))

Runner = Callable[[Sequence[str], Mapping[str, str] | None, Path | None, float],
                  subprocess.CompletedProcess]


class DockerError(MuleboxError):
    """A docker command failed."""

    error_code = "docker.failed"  # common/error_codes.py


class DockerMissing(DockerError):
    """There is no docker command on this machine."""


def default_runner(argv: Sequence[str], env: Mapping[str, str] | None, cwd: Path | None,
                   timeout_s: float) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(list(argv), capture_output=True, text=True, errors="replace",
                              timeout=timeout_s, stdin=subprocess.DEVNULL, env=env, cwd=cwd)
    except FileNotFoundError as exc:
        raise DockerMissing("the docker command is not installed on this machine") from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DockerError(f"`{' '.join(argv[:3])}` failed: {exc}") from exc


class Docker:
    def __init__(self, runner: Runner = default_runner) -> None:
        self._run = runner

    def run(self, *args: str, env: Mapping[str, str] | None = None, cwd: Path | None = None,
            timeout_s: float = CALL_TIMEOUT_S) -> str:
        """`docker <args>`; its stdout, or DockerError with redacted stderr."""
        refused = _REFUSED.intersection(args)
        if (tuple(args[:2]) in _READ_ONLY and refused == {"system"}) or allowed_prune(args):
            refused = set()
        if refused:
            raise DockerError(f"mulebox never runs docker {sorted(refused)[0]}")
        proc = self._run(["docker", *args], env, cwd, timeout_s)
        if proc.returncode != 0:
            detail = Redactor().redact((proc.stderr or "").strip())[-2000:]
            raise DockerError(f"`docker {' '.join(args[:2])}` failed "
                              f"(exit {proc.returncode}): {detail}")
        return proc.stdout or ""

    def lines(self, *args: str, **kwargs: object) -> list[str]:
        """The non-empty lines of stdout, each once, in order."""
        return list(dict.fromkeys(
            line.strip() for line in self.run(*args, **kwargs).splitlines() if line.strip()))
