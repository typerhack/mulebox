"""CLI `mulebox doctor`: is this project ready to run, before anything is uploaded?

Read-only: it reads `.mulebox.yml` and the installed agent skills, and asks the coordinator
what its machines offer. It creates no job. Exit codes: 0 fine or only warnings, 1 a job
would not run, 2 no usable `.mulebox.yml` or client config, 3 build machine unreachable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from mulebox.client import doctor, report, skill_install
from mulebox.client.commands import guarded
from mulebox.client.contract import SCHEMA
from mulebox.client.doctor import FAIL, OK, Facts, Finding
from mulebox.client.remote import CoordinatorError, Remote, request
from mulebox.common.config import (
    ConfigError,
    ProjectConfig,
    find_project_config,
    load_client_config,
    load_project_config,
)
from mulebox.common.protocol import MessageType
from mulebox.common.ssh import RemoteTimeout, SSHUnavailable
from mulebox.version import get_version

EXIT_PROBLEM = 1
TOO_OLD_CODE = "bad_request"  # what a coordinator answers to a request type it does not know


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("doctor", help="check this project and the build machine before "
                            "submitting; read-only")
    parser.add_argument("--json", action="store_true", help="stable keys for tools")
    parser.set_defaults(func=guarded(_doctor))


def _project() -> tuple[ProjectConfig | None, Finding]:
    try:
        path = find_project_config(Path.cwd())
        project = load_project_config(path)
    except ConfigError as exc:  # also: no .mulebox.yml found
        return None, Finding(FAIL, "config", str(exc))
    jobs = ", ".join(project.jobs)
    return project, Finding(OK, "config", f"{path.name} is valid: project {project.project}, "
                            f"jobs {jobs}")


def machine_facts(remote: Remote) -> Facts:
    """What the machine reports; a coordinator too old to answer still says its version."""
    try:
        return dict(remote.call(request(MessageType.MACHINES)).body)
    except CoordinatorError as exc:
        if exc.code != TOO_OLD_CODE:
            raise
    return {"version": remote.version(), "workers": None}


def _about_machines(project: ProjectConfig | None, facts: Facts) -> list[Finding]:
    workers = facts.get("workers")
    if workers is None:
        return [Finding(doctor.WARN, "machine", "the build machine's mulebox is too old to say "
                        "what it offers; upgrade it")]
    return doctor.machines(project, workers) if project else doctor.inventory(workers)


def _about_skill() -> list[Finding]:
    folders = skill_install.config_folders(os.environ, Path.home())
    return doctor.skills(skill_install.inspect_all(folders, skill_install.packaged_text()), SCHEMA)


def examine() -> tuple[list[Finding], int]:
    """(findings, the exit code they call for)."""
    project, about_config = _project()
    findings = [about_config, *_about_skill()]
    code = report.EXIT_USAGE if project is None else 0
    try:
        facts = machine_facts(Remote(load_client_config()))
    except ConfigError as exc:
        return [*findings, Finding(FAIL, "client", str(exc))], report.EXIT_USAGE
    except (SSHUnavailable, RemoteTimeout) as exc:
        reason = f"build machine unreachable: {exc} Tell the user; do not run heavy work here."
        return [*findings, Finding(FAIL, "machine", reason)], code or report.EXIT_UNREACHABLE
    findings += doctor.versions(get_version(), facts)
    findings += _about_machines(project, facts)
    return findings, code or (EXIT_PROBLEM if doctor.worst(findings) == FAIL else 0)


def _doctor(args: argparse.Namespace) -> int:
    findings, code = examine()
    sys.stdout.write(json.dumps(doctor.as_json(findings), indent=2) + "\n" if args.json
                     else doctor.render(findings))
    return code
