"""The one place the worker runs the docker CLI.

No shell is involved. Every call has a timeout, so a hung daemon cannot stop the worker
for good, and errors carry redacted text, because compose output can quote env values.
`prune` and `system` are refused here whatever the caller asks: mulebox removes only what
it found by exact job label (docker_cleanup.py), never by "whatever looks unused". The
runner is injected, and tests use a fake one: they never touch a real Docker daemon.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from mulebox.common.errors import MuleboxError
from mulebox.common.redact import Redactor

CALL_TIMEOUT_S = 60.0
_REFUSED = frozenset({"prune", "system"})

Runner = Callable[[Sequence[str], Mapping[str, str] | None, Path | None, float],
                  subprocess.CompletedProcess]


class DockerError(MuleboxError):
    """A docker command failed."""


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
