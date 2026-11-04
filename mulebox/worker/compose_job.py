"""Getting a job's compose project ready: the file it runs, its env, its first script lines.

The worker asks `docker compose config` for the merged model of the project's files, once
to learn which ports it publishes and once more with those ports in the environment, so a
compose file or `env:` value may use `${MULEBOX_PORT_...}`. The result is rewritten
(compose_file.py) and written next to the checkout, and the job gets only that file through
`COMPOSE_FILE`, with `COMPOSE_PROJECT_NAME`. So `docker compose exec -T api ...` in a job
command needs no flags, from any folder, and cannot reach another project.

Starting the containers is the first thing the job's script does, not a step of the worker.
It therefore runs inside the job's unit: `timeout_min` covers it, a cancel stops it, and
its output goes into the job's log and through redaction like any other output. If the
job fails, the end of the containers' logs goes there too, since they are gone a moment
later. Containers do not run in the unit, so stopping it does not stop them; the worker's
teardown does that on every outcome (cleaner.py), and it runs outside `timeout_min`, so a
job that used all its time still leaves nothing behind.
"""

from __future__ import annotations

import json
import os
import shlex
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mulebox.common import compose
from mulebox.common.compose import ComposeError
from mulebox.worker import compose_file
from mulebox.worker.compose_file import Port
from mulebox.worker.docker import Docker, DockerError
from mulebox.worker.jobspec import port_references
from mulebox.worker.ports import PortPool
from mulebox.worker.reclaim import HELPER_IMAGE

GENERATED_FILE = "compose.mulebox.yml"  # beside src/, so it is not in the project's checkout
LOG_LINES = 50
CONFIG_TIMEOUT_S = 30.0  # this runs in the worker's loop: twice this stays inside a lease

EnvBuilder = Callable[[Mapping[str, str]], dict[str, str]]


@dataclass(frozen=True)
class ComposeJob:
    extra_env: dict[str, str]  # goes into the job's environment
    script: tuple[str, ...]  # runs first in the job's script
    notes: tuple[str, ...]  # told to the job's log


def _config(docker: Docker, env: Mapping[str, str], src: Path) -> dict[str, Any]:
    text = docker.run("compose", "config", "--format", "json", env={**os.environ, **env},
                      cwd=src, timeout_s=CONFIG_TIMEOUT_S)
    try:
        model = json.loads(text)
    except ValueError as exc:
        raise ComposeError(f"docker compose config did not print JSON: {exc}") from exc
    if not isinstance(model, dict):
        raise ComposeError("docker compose config did not print a project")
    return model


def script_lines() -> tuple[str, ...]:
    """Lines at the start of the job's script; `set -e` is already on."""
    helper = shlex.quote(HELPER_IMAGE)
    return (
        f"docker image inspect {helper} >/dev/null 2>&1 || docker pull --quiet {helper}",
        "mulebox_containers() {",
        '  code=$?; trap - EXIT',
        '  if [ "$code" -ne 0 ]; then',
        "    echo 'mulebox: the job failed; the state and last log lines of its containers:'",
        "    docker compose ps --all || true",
        f"    docker compose logs --no-color --tail={LOG_LINES} || true",
        "  fi",
        '  exit "$code"',
        "}",
        "trap mulebox_containers EXIT",
        "docker compose up --detach --wait",
    )


def _port_notes(ports: Sequence[Port], assigned: Mapping[str, int]) -> list[str]:
    return [f"service {port.service} port {port.target}/{port.protocol} is on "
            f"{compose_file.LOOPBACK}:{assigned[port.variable]} (${port.variable})"
            for port in ports]


def prepare(docker: Docker, pool: PortPool, job_id: str, worker: str, files: str, src: Path,
            project_env: Mapping[str, str], build_env: EnvBuilder,
            shared: Sequence[Path] = (), machine_names: Collection[str] = ()) -> ComposeJob:
    """Write the job's compose file; `build_env(extra)` makes the job's environment. `shared`:
    the job's package cache folders, which its services may mount. `machine_names`: the names
    in the machine's `job_env`, which go to services with the value this job has for them."""
    project = compose.project_name(job_id)
    names = compose.split_files(files)
    generated = src.parent / GENERATED_FILE
    if ":" in str(generated):
        raise ComposeError(f"{generated} contains ':', which COMPOSE_FILE cannot hold")
    fixed = {"COMPOSE_PROJECT_NAME": project, "COMPOSE_FILE": compose.join_files(names),
             "UID": str(os.getuid()), "GID": str(os.getgid())}
    unknown = dict.fromkeys(port_references(project_env), "0")
    try:
        first = _config(docker, build_env({**fixed, **unknown}), src)
        ports = compose_file.published_ports(first)
        assigned = pool.take(job_id, {port.variable: port.protocol for port in ports})
        port_env = {name: str(port) for name, port in assigned.items()}
        env = build_env({**fixed, **port_env})
        final = _config(docker, env, src)
        machine_env = {name: env[name] for name in machine_names}
        labels = {compose.LABEL_JOB: job_id, compose.LABEL_WORKER: worker}
        checkout = Path(os.path.realpath(src))
        model, notes = compose_file.rewrite(final, job_id, labels, assigned, checkout, shared,
                                            machine_env)
    except DockerError as exc:
        raise ComposeError(f"the compose files cannot be used: {exc}") from exc
    generated.write_text(json.dumps(model, indent=1), encoding="utf-8")
    src.chmod(0o755)  # a container's user is rarely the worker's user
    return ComposeJob(extra_env={**fixed, **port_env, "COMPOSE_FILE": str(generated)},
                      script=script_lines(),
                      notes=(*_port_notes(ports, assigned), *notes))
