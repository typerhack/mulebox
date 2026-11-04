"""Turning a claimed job into the command and environment that run on the worker.

The job runs as one bash script:

    set -e
    mulebox_step() ...
    mulebox_step setup
    <setup line from .mulebox.yml, if any>
    mulebox_step command
    <job argv, quoted with shlex.join>

`mulebox_step` says which stage starts (steps.py). A `compose:` job has its own lines before
setup (compose_job.py), so setup can use the containers. The setup line is a shell command by design (it comes from the project's
config). The job argv is never re-split: for named jobs the client already sends
`["bash", "-c", "<cmd>"]`, and for `mulebox run -- ...` each argument is quoted, so it
reaches the program unchanged.
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path

from mulebox.common import env_rules
from mulebox.common.errors import MuleboxError
from mulebox.common.status import COMMAND, SETUP
from mulebox.worker import steps


class JobSpecError(MuleboxError):
    """The claimed job's command or settings are unusable."""


def build_script(setup: str | None, argv: Sequence[str], first: Sequence[str] = (),
                 marker: str | None = None) -> str:
    """`marker` turns on the stage marks; without one the script is the plain lines."""
    if isinstance(argv, str) or not argv or not all(isinstance(a, str) for a in argv):
        raise JobSpecError("job argv must be a non-empty list of strings")
    if any("\0" in a for a in argv) or (setup and "\0" in setup):
        raise JobSpecError("job command must not contain NUL characters")
    def mark(stage: str) -> list[str]:
        return [f"{steps.SHELL_NAME} {stage}"] if marker else []

    lines = ["set -e", *([steps.shell_function(marker)] if marker else []), *first]
    if setup and setup.strip():
        lines += [*mark(SETUP), setup]
    lines += [*mark(COMMAND), shlex.join(argv)]
    return "\n".join(lines) + "\n"


def build_argv(setup: str | None, argv: Sequence[str], first: Sequence[str] = (),
               marker: str | None = None) -> tuple[str, ...]:
    return ("bash", "-c", build_script(setup, argv, first, marker))


_REF = env_rules.REFERENCE
_PORT_PREFIX = "MULEBOX_PORT_"


def job_slug(job_id: str) -> str:
    """The job id as a database-friendly name part: lowercase, `_` instead of `-`."""
    return job_id.lower().replace("-", "_")


def in_file_order(env: Mapping[str, str], order: Sequence[str] = ()) -> dict[str, str]:
    """`env` as `.mulebox.yml` lists it. JSON objects are sorted on the wire and in the store,
    so the client sends the order beside them; without it (an older client) the order is
    whatever came, sorted, and anything `order` does not name goes last."""
    first = {name: env[name] for name in order if name in env}
    return {**first, **env}


def port_references(project_env: Mapping[str, str]) -> list[str]:
    """The `${MULEBOX_PORT_...}` names `env:` values use; known only once ports are chosen."""
    found = (name for value in project_env.values() for name in _REF.findall(value))
    return [name for name in found if name.startswith(_PORT_PREFIX)]


def build_env(job_id: str, toolchain_bins: Sequence[Path], base_path: str | None = None,
              project_env: Mapping[str, str] | None = None,
              extra: Mapping[str, str] | None = None,
              machine_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """`machine_env` (`job_env` of node.toml), MULEBOX=1, MULEBOX_JOB_ID, MULEBOX_JOB_SLUG, PATH
    with the toolchains first, then `extra` from the worker, then the project's `env:`
    values. `${NAME}` in a value is replaced by one of those or an earlier `env:` entry (no
    shell is involved); HOME is untouched. `env:` cannot change `extra`, and it can change
    `machine_env`: a project that sets a value knows it best, and can add to the machine's
    with `${NAME}`."""
    base = os.environ.get("PATH", os.defpath) if base_path is None else base_path
    path = os.pathsep.join([*(str(p) for p in toolchain_bins), base])
    env = {**(machine_env or {}), "MULEBOX": "1", "MULEBOX_JOB_ID": job_id,
           "MULEBOX_JOB_SLUG": job_slug(job_id), "PATH": path, **(extra or {})}
    for key, value in (project_env or {}).items():
        if not isinstance(key, str) or not isinstance(value, str) or "\0" in value:
            raise JobSpecError(f"env {key!r}: names and values must be strings without NUL")
        env[key] = _REF.sub(lambda m, known=dict(env): _lookup(known, key, m.group(1)), value)
    return {**env, **(extra or {})}


def _lookup(known: Mapping[str, str], key: str, name: str) -> str:
    if name not in known:
        ports = sorted(n for n in known if n.startswith(_PORT_PREFIX))
        hint = f"; this job's ports: {', '.join(ports)}" if ports else ""
        raise JobSpecError(
            f"env {key}: ${{{name}}} is not a mulebox variable or an earlier env entry{hint}")
    return known[name]


def timeout_seconds(timeout_min: object) -> float:
    if isinstance(timeout_min, bool) or not isinstance(timeout_min, (int, float)):
        raise JobSpecError(f"timeout_min must be a number, got {timeout_min!r}")
    if not 0 < timeout_min <= 24 * 60:
        raise JobSpecError(f"timeout_min out of range: {timeout_min}")
    return float(timeout_min) * 60.0
