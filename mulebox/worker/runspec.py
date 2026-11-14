"""From a claimed job to what the executor runs: command, environment, what to tell the log.

The capabilities a job asks for can change its environment. `compose:` adds its project
(compose_job.py). `needs: [playwright]` points Playwright at one browser folder in the
cache root, so browsers are downloaded once per machine, not once per job, and stay inside
mulebox's roots. What a browser needs from the system cannot be installed from here: it
takes root, so a person does it once, and then adds `playwright` to `capabilities`. A
`cache-*` need gives the job that project's package cache (caches.py).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mulebox.common import compose, config_jobs, env_rules, isolation
from mulebox.common.safepath import ensure_dir
from mulebox.common.config import XCODE
from mulebox.worker import caches, compose_job, isolated, jobspec, simulator, steps, xcode
from mulebox.worker.docker import Docker
from mulebox.worker.executor import ExecutorError, RunSpec, unit_name
from mulebox.worker.paths import NodePaths
from mulebox.worker.ports import PortPool

PLAYWRIGHT_CAPABILITY = "playwright"
PLAYWRIGHT_SETTINGS = {
    # An install removes every browser whose project folder is gone, and a job's checkout always
    # is, so without this each job deleted what the jobs before it had downloaded.
    "PLAYWRIGHT_SKIP_BROWSER_GC": "1",
    # Its default is 30 s of silence, then a new attempt from zero; a slow link stalls longer.
    "PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT": "120000",
}
PNPM_NO_CHECK = ("pnpm_config_verify_deps_before_run", "npm_config_verify_deps_before_run")
COORDINATOR_LIMITS = "coordinator"  # `limits` in claim_ok, coordinator/attendance.py


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
    return {"PLAYWRIGHT_BROWSERS_PATH": str(browsers), **PLAYWRIGHT_SETTINGS}


def _pnpm_settled(claim: dict[str, Any]) -> dict[str, str]:
    """pnpm can check a project's packages before each `pnpm run` and start a long, silent install.
    Once this job's `install` or `setup` has settled them there is nothing left to check."""
    if not claim.get("deps_settled"):
        return {}
    if "pnpm" not in (claim.get("toolchain") or {}) and "cache-pnpm" not in (claim.get("needs") or ()):
        return {}
    return dict.fromkeys(PNPM_NO_CHECK, "false")


def _check_names(values: Mapping[str, str], for_compose: bool) -> None:
    for name in values:
        problem = env_rules.problem(name, for_compose)
        if problem:
            raise jobspec.JobSpecError(f"env {name} {problem}")


def _host_ports(machine: Machine, job_id: str, names: str | None) -> dict[str, str]:
    """Free ports for processes of the job itself; held for it until it is cleaned up. The
    worker checks the names again: it cannot know which client sent the job."""
    wanted = config_jobs.split_ports(names or "")
    for name in wanted:
        problem = config_jobs.port_problem(name)
        if problem:
            raise jobspec.JobSpecError(f"port {name} {problem}")
    taken = machine.ports.take(job_id, {config_jobs.port_variable(n): "tcp" for n in wanted})
    return {name: str(port) for name, port in taken.items()}


def _runtime_limit(claim: dict[str, Any]) -> float | None:
    """No limit when the coordinator runs the job's time limits; an older one does not, so
    `timeout_min` stays a hard limit there and no job can run forever."""
    if claim.get("limits") == COORDINATOR_LIMITS:
        return None
    return jobspec.timeout_seconds(claim["timeout_min"])


def _simulator(job_id: str, claim: dict[str, Any]) -> tuple[str, ...]:
    """The lines that make the job's own simulator, if it asks for one (simulator.py), from
    the runtimes its Xcode can use: the pinned one (its `DEVELOPER_DIR` is the job's), else
    the newest."""
    if not simulator.wanted(claim):
        return ()
    pinned = (claim.get("toolchain") or {}).get(XCODE)
    return simulator.for_job(claim, xcode.runtimes(pinned), job_id,
                             None if pinned else xcode.newest_developer_dir())


def build(machine: Machine, job_id: str, claim: dict[str, Any], src: Path, log_path: Path,
          bins: Sequence[Path], marker: str = "", scratch: Path | None = None
          ) -> tuple[RunSpec, tuple[str, ...]]:
    """(the run spec, notes for the job's log). `marker`: of the job's StepTracker; `scratch`:
    the job's own folder, for what must not land in the project's."""
    values = jobspec.in_file_order(claim.get("env") or {}, claim.get("env_order") or ())
    files = values.pop(compose.COMPOSE_FILES_KEY, None)
    names = values.pop(config_jobs.HOST_PORTS_KEY, None)
    image = values.pop(isolation.IMAGE_KEY, None)
    _check_names(values, files is not None)
    needs = claim.get("needs") or ()
    cached = caches.for_job(machine.paths, claim["project"], needs)
    own = _host_ports(machine, job_id, names)
    settled = _pnpm_settled(claim)
    base = {**_capability_env(machine, needs), **cached.env, **own, **settled,
            **xcode.env_for(claim.get("toolchain") or {}), **xcode.derived_data_env(scratch)}

    def environment(extra: dict[str, str]) -> dict[str, str]:
        return jobspec.build_env(job_id, bins, project_env=values, extra={**base, **extra},
                                 machine_env=machine.job_env)

    first: tuple[str, ...] = ()
    extra: dict[str, str] = {}
    notes: tuple[str, ...] = ()
    if files is not None and isolation.CAPABILITY in needs:
        raise ExecutorError("an isolated job cannot use compose: on this mulebox yet")
    if files is not None:
        if machine.docker is None:
            raise ExecutorError("this worker has no Docker to run a compose: project")
        ready = compose_job.prepare(machine.docker, machine.ports, job_id, machine.name, files,
                                    src, values, environment, cached.folders,
                                    (*machine.job_env, *settled), scratch)
        first, extra, notes = ready.script, ready.extra_env, ready.notes
    first = (*_simulator(job_id, claim), *first)
    spec = RunSpec(name=unit_name(job_id),
                   argv=jobspec.build_argv(claim.get("setup"), claim["argv"], first,
                                           marker or steps.new_marker(), claim.get("install")),
                   cwd=src, env=environment(extra), log_path=log_path,
                   timeout_s=_runtime_limit(claim))
    if isolation.CAPABILITY in needs:
        spec, notes = _isolate(machine, job_id, claim, spec, image, bins, cached.folders, notes)
    ports = (f"port {port} is ${name}" for name, port in own.items())
    return spec, (*cached.notes, *ports, *notes)


def _isolate(machine: Machine, job_id: str, claim: dict[str, Any], spec: RunSpec,
             image: str | None, bins: Sequence[Path], cache_folders: Sequence[Path],
             notes: tuple[str, ...]) -> tuple[RunSpec, tuple[str, ...]]:
    """The job in its own container (isolated.py); its toolchains and browsers read-only."""
    if machine.docker is None:
        raise ExecutorError("this worker has no Docker to run an isolated job")
    if image is not None and (problem := isolation.image_problem(image)):
        raise jobspec.JobSpecError(f"image {problem}")
    repo = machine.paths.project_home(claim["project"]) / "repo.git"
    read_only = [machine.paths.toolchains_dir()]
    if PLAYWRIGHT_CAPABILITY in (claim.get("needs") or ()):
        read_only.append(machine.paths.browsers_dir())
    wrapped = isolated.wrap(spec, job_id, machine.name, image=image, bins=bins,
                            read_write=[repo, *cache_folders], read_only=read_only)
    return wrapped, (isolated.note(image, bool(cache_folders)), *notes)
