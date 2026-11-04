"""From a claimed job to what the executor runs: command, environment, what to tell the log.

The capabilities a job asks for can change its environment. `compose:` adds its project
(compose_job.py). `needs: [playwright]` points Playwright at one browser folder in the
cache root, so browsers are downloaded once per machine, not once per job, and stay inside
mulebox's roots. What a browser needs from the system cannot be installed from here: it
takes root, so a person does it once, and then adds `playwright` to `capabilities`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mulebox.common import compose, env_rules
from mulebox.common.safepath import ensure_dir
from mulebox.worker import compose_job, jobspec
from mulebox.worker.docker import Docker
from mulebox.worker.executor import ExecutorError, RunSpec, unit_name
from mulebox.worker.paths import NodePaths
from mulebox.worker.ports import PortPool

PLAYWRIGHT_CAPABILITY = "playwright"


@dataclass(frozen=True)
class Machine:
    """What of this worker a job's preparation uses."""
    name: str
    paths: NodePaths
    docker: Docker | None
    ports: PortPool
    job_env: Mapping[str, str] = field(default_factory=dict)


def _capability_env(machine: Machine, needs: Sequence[str]) -> dict[str, str]:
    if PLAYWRIGHT_CAPABILITY not in needs:
        return {}
    browsers = ensure_dir(machine.paths.browsers_dir(), machine.paths.roots)
    return {"PLAYWRIGHT_BROWSERS_PATH": str(browsers)}


def _check_names(values: Mapping[str, str], for_compose: bool) -> None:
    for name in values:
        problem = env_rules.problem(name, for_compose)
        if problem:
            raise jobspec.JobSpecError(f"env {name} {problem}")


def build(machine: Machine, job_id: str, claim: dict[str, Any], src: Path, log_path: Path,
          bins: Sequence[Path]) -> tuple[RunSpec, tuple[str, ...]]:
    """(the run spec, notes for the job's log)."""
    values = dict(claim.get("env") or {})
    files = values.pop(compose.COMPOSE_FILES_KEY, None)
    _check_names(values, files is not None)
    base = _capability_env(machine, claim.get("needs") or ())

    def environment(extra: dict[str, str]) -> dict[str, str]:
        return jobspec.build_env(job_id, bins, project_env=values, extra={**base, **extra},
                                 machine_env=machine.job_env)

    first: tuple[str, ...] = ()
    extra: dict[str, str] = {}
    notes: tuple[str, ...] = ()
    if files is not None:
        if machine.docker is None:
            raise ExecutorError("this worker has no Docker to run a compose: project")
        ready = compose_job.prepare(machine.docker, machine.ports, job_id, machine.name, files,
                                    src, values, environment)
        first, extra, notes = ready.script, ready.extra_env, ready.notes
    spec = RunSpec(name=unit_name(job_id),
                   argv=jobspec.build_argv(claim.get("setup"), claim["argv"], first),
                   cwd=src, env=environment(extra), log_path=log_path,
                   timeout_s=jobspec.timeout_seconds(claim["timeout_min"]))
    return spec, notes
