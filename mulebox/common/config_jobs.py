"""The `jobs:` table of `.mulebox.yml`: a job is a command, or a command with settings.

    jobs:
      check: pnpm check
      lint:
        run: pnpm lint
        setup: false       # or another command; default: the top-level `setup`
        install: false     # the same for the top-level `install`
        compose: false     # no containers for this job; default: the top-level `compose`
      e2e:
        run: pnpm e2e
        ports: [vite]      # a free port for a process of the job itself, MULEBOX_PORT_VITE

A plain string is a job with the defaults, so a file without settings means what it always
did. `setup` and the compose file list already go with every job, so those are only what the
client sends (`for_job`). The names of `ports:` travel the way the compose list does, inside the
job's `env`; the worker takes them out, and chooses the ports (runspec.py, ports.py).

A compose port's variable always ends in the container port (compose_file.py), so a name that
ends in a number is refused: it could say the same thing as a port of a service.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Any

from mulebox.common import env_rules
from mulebox.common.config_reader import Reader

PORT_PREFIX = "MULEBOX_PORT_"
HOST_PORTS_KEY = "MULEBOX_HOST_PORTS"
NO_SETUP = ""
_PORT_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_LIKE_A_SERVICE_PORT = re.compile(r"[_-]\d+([_-]udp)?$", re.IGNORECASE)
_SEPARATOR = ","


@dataclass(frozen=True)
class JobOptions:
    setup: str | None = None  # None: the top-level setup; NO_SETUP: none
    install: str | None = None  # the same
    compose: bool = True
    ports: tuple[str, ...] = ()


def port_problem(name: str) -> str | None:
    """Why `name` cannot be a job's port, or None."""
    if not _PORT_NAME.fullmatch(name):
        return "must start with a letter and hold only letters, digits, - and _"
    if _LIKE_A_SERVICE_PORT.search(name):
        return "must not end in a port number, which could clash with a compose service's port"
    return None


def port_variable(name: str) -> str:
    return PORT_PREFIX + name.upper().replace("-", "_")


def join_ports(names: tuple[str, ...]) -> str:
    return _SEPARATOR.join(names)


def split_ports(value: str) -> tuple[str, ...]:
    return tuple(name for name in value.split(_SEPARATOR) if name)


def _ports(entry: Reader) -> tuple[str, ...]:
    names = entry.strings("ports")
    for index, name in enumerate(names):
        problem = port_problem(name)
        if problem:
            entry.fail(f"ports[{index}]", problem)
    variables = [port_variable(name) for name in names]
    if len(set(variables)) < len(variables):
        entry.fail("ports", "names the same port twice")
    return names


def _line(entry: Reader, name: str) -> str | None:
    if entry.get(name, None) is False:
        return NO_SETUP
    return entry.text(name, None)


def read_jobs(reader: Reader) -> tuple[dict[str, str], dict[str, JobOptions]]:
    """(job name -> command, job name -> settings of the jobs that have any)."""
    sub = reader.table("jobs", required=True)
    commands: dict[str, str] = {}
    options: dict[str, JobOptions] = {}
    for name in sub.data:
        if not isinstance(name, str) or not name.strip():
            sub.fail_at("jobs", f"keys must be non-empty strings, got {name!r}")
        if not isinstance(sub.data[name], dict):
            commands[name] = sub.text(name)
            continue
        entry = sub.table(name)
        commands[name] = entry.text("run")
        options[name] = JobOptions(setup=_line(entry, "setup"), install=_line(entry, "install"),
                                   compose=entry.boolean("compose", True), ports=_ports(entry))
        entry.finish()
    if "check" not in commands:
        reader.fail("jobs", "must define a 'check' job")
    return commands, options


def for_job(project: Any, name: str | None) -> tuple[Any, list[str]]:
    """(`project` as job `name` sees it, the `env:` entries it cannot have); None is `mulebox
    run`. A job without containers has no compose port, and a job has none of another job's
    `ports:`: an entry built on one goes, not the whole job."""
    options = project.job_options.get(name, JobOptions())
    setup = project.setup if options.setup is None else options.setup or None
    install = project.install if options.install is None else options.install or None
    files = project.compose if options.compose else ()
    own = {port_variable(port) for port in options.ports}
    others = {port_variable(port) for job in project.job_options.values() for port in job.ports}

    def gone(used: str) -> bool:
        if used in own:
            return False
        return used in others or bool(project.compose and not files
                                      and used.startswith(PORT_PREFIX))

    env, dropped = env_rules.without(project.env, gone)
    return dataclasses.replace(project, setup=setup, install=install, compose=files, env=env,
                               host_ports=options.ports), dropped
