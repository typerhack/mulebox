"""`mulebox contract`: how to work in this project through mulebox, for an agent to read.

Generated, not written: the facts come from `.mulebox.yml` and from the tables the code
itself uses, so there is no second copy to drift. It reads no network, so it still
answers when the build machine is down, which is when an agent most needs its rules.
`schema` rises when a key is removed or changes meaning, and when the skill has to teach
something new, because that is how an installed skill finds out it is behind: SKILL.md says
which schema it was written for (tests/test_skill.py ties the two). Adding keys alone is safe.
"""

from __future__ import annotations

from typing import Any

from mulebox.client import report
from mulebox.client.excludes import BUILTIN_EXCLUDES
from mulebox.common.config import ProjectConfig

# 2: `project.services` removed; `project.needs` includes what compose implies
# 3: the skill teaches detached jobs and events, and says the schema it was written for
SCHEMA = 3
FULL_GATE = "check"
Contract = dict[str, Any]

COMMANDS = {
    "before_the_first_job": "mulebox doctor",
    "full_gate": "mulebox check",
    "one_job": "mulebox check <job>",
    "one_off": "mulebox run -- <cmd> <args...>",
    "leave_running": "mulebox check --detach",
    "follow_it": "mulebox events --job <job-id> --json",
    "its_state": "mulebox status <job-id>",
    "its_result": "mulebox wait <job-id>",
    "queue": "mulebox queue",
    "all_projects": "mulebox projects",
    "read_log": "mulebox logs <job-id>",
    "why_it_failed": "mulebox logs <job-id> --summary",
    "cancel": "mulebox cancel <job-id>",
    "report_a_problem": "mulebox feedback draft <job-id> --summary <text>",
    "skill_status": "mulebox skill status",
}
THROUGH_MULEBOX = ("builds", "type checks", "lint", "tests")
KEEP_LOCAL = ("git", "search", "reading files", "diffs")
EXIT_CODES = (
    (report.EXIT_USAGE, "config or usage error", "fix .mulebox.yml or the command"),
    (report.EXIT_UNREACHABLE, "build machine unreachable, or the live view lost it",
     "tell the user; if a job id was printed, get its result with mulebox wait later"),
    (report.EXIT_REMOTE, "the build machine refused the request",
     "read the message and tell the user"),
    (report.EXIT_NOT_STARTED, "the job could not start, so no project code ran",
     "not a failed check: read the reason in the log; mulebox doctor checks most causes"),
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
COMPOSE = (
    "mulebox starts the compose files' containers before setup and removes them, with their "
    "networks and volumes, after every job; never run docker compose up or down yourself",
    "use docker compose exec -T <service> ... in setup and jobs; -T is required, and no -f "
    "or -p: the project is already selected",
    "published ports move: read MULEBOX_PORT_<SERVICE>_<PORT> or use it in env:, never a "
    "port number from a compose file; the address is 127.0.0.1",
)
EVENTS = (
    "mulebox events prints one JSON line per state change and no log; it exits when the job "
    "ends, with the job's exit code, and survives a dropped connection",
    "every line has v, event, job_id and state; ignore events and keys you do not know",
    "queued has position, waiting_for and estimate_s (how long this job usually runs, from "
    "its past runs; null when unknown; an estimate, not a promise, and not the time in line); "
    "started has machine; finished has outcome, exit_code and duration_s",
    "after finished, read mulebox logs <job-id> --summary if the job failed",
)
RULES = (
    "if mulebox is unreachable, stop and tell the user; never run heavy commands locally",
    "if this contract's schema is higher than the one your mulebox skill says it was written "
    "for, tell the user the skill is behind and that mulebox skill update fixes it; never "
    "update the skill yourself",
    "a detached job keeps running without you, within timeout_min: cancel it with mulebox "
    "cancel if you no longer want it, nobody else will",
    "run mulebox doctor before a project's first job, and after changing toolchain or needs: "
    "it finds what a job would fail on, before anything is uploaded; it exits 1 if a job "
    "would not run, and warnings alone exit 0",
    "a failed job ends with a short summary on stderr: read it first, and the full log only "
    "if it is not enough",
    "do not ssh into the build machine to change, install or delete things",
    "put no real secrets, hosts or personal paths in .mulebox.yml or workflows",
    "every database name must include ${MULEBOX_JOB_SLUG}; never use an existing database",
    "waiting in the queue is normal; do not cancel and resubmit to speed it up; if the wait "
    "may be long, run the job detached",
    "do not cancel other people's jobs",
    "a missing toolchain error lists the versions the machine has: switch to one only if it "
    "matches the project, otherwise ask the user to install the version the project needs",
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
        "events": list(EVENTS),
        "git": list(GIT), "never_uploaded": [*BUILTIN_EXCLUDES, *exclude],
        "compose": list(COMPOSE) if config and config.compose else [],
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
    if project["needs"]:
        lines += ["", f"Needs a build machine with: {', '.join(project['needs'])}"]
    if project["compose"]:
        lines += ["", f"Compose files: {', '.join(project['compose'])}"]
    return lines


def render(contract: Contract) -> str:
    """The contract as plain text; `--json` gives the same facts with stable keys."""
    lines = [f"mulebox {contract['mulebox_version']} contract, schema {contract['schema']}", "",
             *_project_text(contract["project"]), "", "Commands:"]
    lines += [f"- {name.replace('_', ' ')}: {text}" for name, text in contract["commands"].items()]
    lines += ["", "Events:", *_bullets(contract["events"]),
              "", f"Through mulebox: {', '.join(contract['through_mulebox'])}",
              f"Keep local: {', '.join(contract['keep_local'])}", "", "Git:",
              *_bullets(contract["git"]),
              *(["", "Containers:", *_bullets(contract["compose"])] if contract["compose"] else []),
              "", "Never uploaded:",
              ", ".join(contract["never_uploaded"]), "",
              "Exit codes (otherwise the job's own code):"]
    lines += [f"- {e['code']}: {e['meaning']}. {e['action']}." for e in contract["exit_codes"]]
    lines += ["", "Rules:", *_bullets(contract["rules"])]
    return "\n".join(lines) + "\n"
