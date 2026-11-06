"""CLI `mulebox doctor`: is this project ready to run, before anything is uploaded?

Read-only: it reads `.mulebox.yml`, the project's compose files and the installed agent
skills, and asks the coordinator what its machines offer. It creates no job. Exit codes: 0 fine or only warnings, 1 a job
would not run, 2 no usable `.mulebox.yml` or client config, 3 build machine unreachable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from mulebox.client import compose_check, doctor, gitinfo, report, skill_install
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
MAX_REGISTRIES = 8  # what a coordinator takes in one request
TOO_OLD_CODE = "bad_request"  # what a coordinator answers to a request type it does not know


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("doctor", help="check this project and the build machine before "
                            "submitting; read-only")
    parser.add_argument("--json", action="store_true", help="stable keys for tools")
    parser.set_defaults(func=guarded(_doctor, notices=True))


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


def _about_registries(project: ProjectConfig | None, remote: Remote) -> list[Finding]:
    if project is None or not project.compose:
        return []
    root = find_project_config(Path.cwd()).parent
    hosts = compose_check.registries(project.compose, root)[:MAX_REGISTRIES]
    try:
        reply = remote.call(request(MessageType.REACH, hosts=hosts)) if hosts else None
    except CoordinatorError as exc:
        if exc.code != TOO_OLD_CODE:
            raise
        reply = None
    return doctor.registries(reply.body["hosts"]) if reply else []


def _about_skill() -> list[Finding]:
    folders = skill_install.config_folders(os.environ, Path.home())
    return doctor.skills(skill_install.inspect_all(folders, skill_install.packaged_text()), SCHEMA)


def _about_git(project: ProjectConfig | None) -> list[Finding]:
    """What `check` would refuse before any upload. Without a project there is no folder."""
    if project is None:
        return []
    root = find_project_config(Path.cwd()).parent
    try:
        gitinfo.ensure_worktree(root)
        gitinfo.ensure_commit(root)
    except gitinfo.GitError as exc:
        return [Finding(doctor.FAIL, "git", str(exc))]
    return []


def _about_compose(project: ProjectConfig | None) -> list[Finding]:
    if project is None:
        return []
    return compose_check.findings(project.compose, find_project_config(Path.cwd()).parent)


def examine() -> tuple[list[Finding], int]:
    """(findings, the exit code they call for)."""
    project, about_config = _project()
    findings = [about_config, *(doctor.env_references(project) if project else ()),
                *_about_git(project), *_about_compose(project), *_about_skill()]
    code = report.EXIT_USAGE if project is None else 0
    try:
        remote = Remote(load_client_config())
        facts = machine_facts(remote)
        reached = _about_registries(project, remote)
    except ConfigError as exc:
        return [*findings, Finding(FAIL, "client", str(exc))], report.EXIT_USAGE
    except (SSHUnavailable, RemoteTimeout) as exc:
        reason = f"build machine unreachable: {exc} Tell the user; do not run heavy work here."
        return [*findings, Finding(FAIL, "machine", reason)], code or report.EXIT_UNREACHABLE
    findings += doctor.versions(get_version(), facts)
    findings += _about_machines(project, facts) + reached
    findings += doctor.disks(facts.get("workers") or [])
    findings += doctor.dashboard(facts)
    return findings, code or (EXIT_PROBLEM if doctor.worst(findings) == FAIL else 0)


def _doctor(args: argparse.Namespace) -> int:
    findings, code = examine()
    sys.stdout.write(json.dumps(doctor.as_json(findings), indent=2) + "\n" if args.json
                     else doctor.render(findings))
    return code
