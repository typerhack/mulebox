"""Turning a claimed job into the command and environment that run on the worker.

The job runs as one bash script:

    set -e
    <setup line from .mulebox.yml, if any>
    <job argv, quoted with shlex.join>

The setup line is a shell command by design (it comes from the project's config). The job
argv is never re-split: for named jobs the client already sends `["bash", "-c", "<cmd>"]`,
and for `mulebox run -- ...` each argument is quoted, so it reaches the program unchanged.
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Sequence
from pathlib import Path

from mulebox.common.errors import MuleboxError


class JobSpecError(MuleboxError):
    """The claimed job's command or settings are unusable."""


def build_script(setup: str | None, argv: Sequence[str]) -> str:
    if isinstance(argv, str) or not argv or not all(isinstance(a, str) for a in argv):
        raise JobSpecError("job argv must be a non-empty list of strings")
    if any("\0" in a for a in argv) or (setup and "\0" in setup):
        raise JobSpecError("job command must not contain NUL characters")
    lines = ["set -e"]
    if setup and setup.strip():
        lines.append(setup)
    lines.append(shlex.join(argv))
    return "\n".join(lines) + "\n"


def build_argv(setup: str | None, argv: Sequence[str]) -> tuple[str, ...]:
    return ("bash", "-c", build_script(setup, argv))


def build_env(job_id: str, toolchain_bins: Sequence[Path], base_path: str | None = None,
              ) -> dict[str, str]:
    """MULEBOX=1, MULEBOX_JOB_ID and PATH with the toolchains first; HOME is untouched."""
    base = os.environ.get("PATH", os.defpath) if base_path is None else base_path
    path = os.pathsep.join([*(str(p) for p in toolchain_bins), base])
    return {"MULEBOX": "1", "MULEBOX_JOB_ID": job_id, "PATH": path}


def timeout_seconds(timeout_min: object) -> float:
    if isinstance(timeout_min, bool) or not isinstance(timeout_min, (int, float)):
        raise JobSpecError(f"timeout_min must be a number, got {timeout_min!r}")
    if not 0 < timeout_min <= 24 * 60:
        raise JobSpecError(f"timeout_min out of range: {timeout_min}")
    return float(timeout_min) * 60.0
