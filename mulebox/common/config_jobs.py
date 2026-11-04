"""The `jobs:` table of `.mulebox.yml`: a job is a command, or a command with settings.

    jobs:
      check: pnpm check
      lint:
        run: pnpm lint
        setup: false       # or another command; default: the top-level `setup`
        compose: false     # no containers for this job; default: the top-level `compose`

A plain string is a job with the defaults, so a file without settings means what it always
did. The worker needs no change for this: `setup` and the compose file list already go with
every job, so a job's settings are only what the client sends (`for_job`).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from mulebox.common import env_rules
from mulebox.common.config_reader import Reader

PORT_PREFIX = "MULEBOX_PORT_"
NO_SETUP = ""


@dataclass(frozen=True)
class JobOptions:
    setup: str | None = None  # None: the top-level setup; NO_SETUP: none
    compose: bool = True


def _setup(entry: Reader) -> str | None:
    if entry.get("setup", None) is False:
        return NO_SETUP
    return entry.text("setup", None)


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
        options[name] = JobOptions(setup=_setup(entry), compose=entry.boolean("compose", True))
        entry.finish()
    if "check" not in commands:
        reader.fail("jobs", "must define a 'check' job")
    return commands, options


def for_job(project: Any, name: str) -> tuple[Any, list[str]]:
    """(`project` as job `name` sees it, the `env:` entries it cannot have). Without containers
    a job has no `MULEBOX_PORT_...`, so an entry built on one goes, not the whole job."""
    options = project.job_options.get(name)
    if options is None:
        return project, []
    setup = project.setup if options.setup is None else options.setup or None
    files = project.compose if options.compose else ()
    env, dropped = project.env, []
    if project.compose and not files:
        env, dropped = env_rules.without(env, lambda used: used.startswith(PORT_PREFIX))
    return dataclasses.replace(project, setup=setup, compose=files, env=env), dropped
