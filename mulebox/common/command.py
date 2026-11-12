"""Running a short system command (systemctl, launchctl, ps, sysctl) with captured text output.

The one place such a call is made, so every caller gets a timeout, no stdin, and an error of
its own kind for a command that cannot run at all. A non-zero exit is not an error here: the
caller reads `returncode`, as many of these commands use it to answer a question.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Sequence

from mulebox.common.errors import MuleboxError

TIMEOUT_S = 60

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


class CommandError(MuleboxError):
    """A command could not be run, or did not end in time."""


def run(argv: Sequence[str], timeout_s: float = TIMEOUT_S,
        error: type[MuleboxError] = CommandError,
        env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess:
    """`env`, when given, is the whole environment of the command."""
    try:
        return subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout_s,
                              stdin=subprocess.DEVNULL, check=False,
                              env=None if env is None else dict(env))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise error(f"`{' '.join(argv[:3])}` failed: {exc}") from exc
