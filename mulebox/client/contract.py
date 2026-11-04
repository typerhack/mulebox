"""`mulebox contract`: how to work in this project through mulebox, for an agent to read.

Generated, not written: the facts come from `.mulebox.yml` and from the tables the code
itself uses, so there is no second copy to drift. It reads no network, so it still
answers when the build machine is down, which is when an agent most needs its rules.
`schema` changes only when a key is removed or changes meaning; adding keys is safe.
"""

from __future__ import annotations

from typing import Any

from mulebox.client import report
from mulebox.client.excludes import BUILTIN_EXCLUDES
from mulebox.common.config import ProjectConfig

SCHEMA = 2  # 2: `project.services` removed; `project.needs` includes what compose implies
FULL_GATE = "check"
Contract = dict[str, Any]

COMMANDS = {
    "full_gate": "mulebox check",
    "one_job": "mulebox check <job>",
    "one_off": "mulebox run -- <cmd> <args...>",
    "queue": "mulebox queue",
    "all_projects": "mulebox projects",
    "read_log": "mulebox logs <job-id>",
    "cancel": "mulebox cancel <job-id>",
    "report_a_problem": "mulebox feedback draft <job-id> --summary <text>",
}
THROUGH_MULEBOX = ("builds", "type checks", "lint", "tests")
KEEP_LOCAL = ("git", "search", "reading files", "diffs")
EXIT_CODES = (
    (report.EXIT_USAGE, "config or usage error", "fix .mulebox.yml or the command"),
    (report.EXIT_UNREACHABLE, "build machine unreachable, or the live view lost it",
     "tell the user; if a job id was printed, read it with mulebox logs later"),
    (report.EXIT_REMOTE, "the build machine refused the request",
     "read the message and tell the user"),
    (report.EXIT_INTERRUPTED, "interrupted on the build machine", "run it again once"),
    (report.EXIT_TIMED_OUT, "the job hit timeout_min",
     "look for a hang; raise timeout_min only if the work needs it"),
    (report.EXIT_CANCELLED, "cancelled", "nothing to do"),
)
GIT = (
    "git stays local; mulebox never commits, pushes or changes the branch",
    "a job runs on a snapshot of the worktree: tracked and untracked files git does not "
    "ignore, so uncommitted changes are included and nothing needs committing first",
    "a stale warning means files changed while the job ran: run it again",
)
RULES = (
    "if mulebox is unreachable, stop and tell the user; never run heavy commands locally",
    "do not ssh into the build machine to change, install or delete things",
    "put no real secrets, hosts or personal paths in .mulebox.yml or workflows",
    "every database name must include ${MULEBOX_JOB_SLUG}; never use an existing database",
    "waiting in the queue is normal; do not cancel and resubmit to speed it up",
    "do not cancel other people's jobs",
    "show the user a feedback draft and get their approval before mulebox feedback post",
)


def _project(config: ProjectConfig) -> dict[str, Any]:
    return {"name": config.project, "jobs": dict(config.jobs), "full_gate": FULL_GATE,
            "setup": config.setup, "toolchain": dict(config.toolchain),
            "needs": list(config.all_needs), "compose": list(config.compose),
            "timeout_min": config.timeout_min}


def build(config: ProjectConfig | None, version: str) -> Contract:
    """The contract; `project` is None outside a project set up for mulebox."""
    exclude = config.exclude if config else ()
    return {
        "schema": SCHEMA, "mulebox_version": version,
        "project": _project(config) if config else None,
        "commands": dict(COMMANDS),
        "through_mulebox": list(THROUGH_MULEBOX), "keep_local": list(KEEP_LOCAL),
        "git": list(GIT), "never_uploaded": [*BUILTIN_EXCLUDES, *exclude],
        "exit_codes": [{"code": code, "meaning": meaning, "action": action}
                       for code, meaning, action in EXIT_CODES],
        "rules": list(RULES),
    }


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def _project_text(project: dict[str, Any] | None) -> list[str]:
    if project is None:
        return ["No .mulebox.yml here: this project is not set up for mulebox yet.",
                "Setup steps: mulebox's docs/agents.md, section 2."]
    lines = [f"Project: {project['name']} (timeout {project['timeout_min']} min)"]
    if project["setup"]:
        lines.append(f"Setup before every job: {project['setup']}")
    lines += ["", "Jobs:"]
    for name, command in project["jobs"].items():
        run = "mulebox check" if name == FULL_GATE else f"mulebox check {name}"
        lines.append(f"- {run}: {command}")
    return lines


def render(contract: Contract) -> str:
    """The contract as plain text; `--json` gives the same facts with stable keys."""
    lines = [f"mulebox {contract['mulebox_version']} contract", "",
             *_project_text(contract["project"]), "", "Commands:"]
    lines += [f"- {name.replace('_', ' ')}: {text}" for name, text in contract["commands"].items()]
    lines += ["", f"Through mulebox: {', '.join(contract['through_mulebox'])}",
              f"Keep local: {', '.join(contract['keep_local'])}", "", "Git:",
              *_bullets(contract["git"]), "", "Never uploaded:",
              ", ".join(contract["never_uploaded"]), "",
              "Exit codes (otherwise the job's own code):"]
    lines += [f"- {e['code']}: {e['meaning']}. {e['action']}." for e in contract["exit_codes"]]
    lines += ["", "Rules:", *_bullets(contract["rules"])]
    return "\n".join(lines) + "\n"
