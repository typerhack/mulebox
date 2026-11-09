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
from mulebox.common.config import DEFAULT_LOG_DAYS, ProjectConfig
from mulebox.common.config_jobs import for_job, port_variable
from mulebox.common.status import STAGES

# 2: `project.services` removed; `project.needs` includes what compose implies
# 3: the skill teaches detached jobs and events, and says the schema it was written for
# 4: the skill teaches package caches, stages, `usual` and log retention
# 5: timeout_min is a check-in; the skill teaches check-ins, unattended jobs and exit 76
# 6: a job may have settings; `project.job_settings`
# 7: `job_settings` has `ports`
# 8: `cache-npm`, `cache-pip`, `stage` events, `last_line`, `running_ahead`, activity is the job's own
# 9: no unattended rule: a check_in is a question, `mulebox ok` answers it, a stuck job with no
#    answer stops, results wait for an absent agent, and `check` does not repeat a tested job
# 10: jobs of different branches run at once, one branch waits in line, `branch_busy`
# 11: a job installs its own pinned toolchain
# 12: `project.install`, `mulebox warm`, an `install` stage, and exit 5 when `install` fails
# 13: `take_it_back` is gone: it was `its_result` under a second name
# 14: `mulebox run --in <service>`
# 15: a `toolchain` stage, only when a job installs a pinned one
SCHEMA = 15
FULL_GATE = "check"
Contract = dict[str, Any]

COMMANDS = {
    "before_the_first_job": "mulebox doctor",
    "full_gate": "mulebox check",
    "one_job": "mulebox check <job>",
    "one_off": "mulebox run -- <cmd> <args...>",
    "one_off_in_a_service": "mulebox run --in <service> -- <cmd> <args...>",
    "one_off_bare": "mulebox run --bare -- <cmd> <args...>",
    "bring_files_back": "mulebox run --take <path> -- <cmd> <args...>",
    "leave_running": "mulebox check --detach",
    "prepare_ahead": "mulebox warm [job]",
    "follow_it": "mulebox events --job <job-id> --json",
    "its_state": "mulebox status <job-id>",
    "its_result": "mulebox wait <job-id>",
    "queue": "mulebox queue",
    "all_projects": "mulebox projects",
    "read_log": "mulebox logs <job-id>",
    "why_it_failed": "mulebox logs <job-id> --summary",
    "cancel": "mulebox cancel <job-id>",
    "report_a_problem": "mulebox feedback guide",
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
    (report.EXIT_STOPPED, "stopped: stuck; it did nothing and nobody answered its question",
     "not a failed check: nothing is known about the code, so find what hangs and run it again"),
    (report.EXIT_TIMED_OUT, "the job hit a hard timeout_min on a build machine older than 0.37",
     "look for a hang; a current machine has no such limit, it sends check-ins"),
    (report.EXIT_CANCELLED, "cancelled", "nothing to do"),
)
GIT = (
    "git stays local; mulebox never commits, pushes or changes the branch",
    "a job runs on a snapshot of the worktree: tracked and untracked files git does not "
    "ignore, so uncommitted changes are included and nothing needs committing first",
    "a stale warning means files changed while the job ran: run it again",
    "a job has no git history: checks that read it, such as commitlint or a diff against main, "
    "stay local",
)
COMPOSE = (
    "mulebox starts the compose files' containers before setup and removes them, with their "
    "networks and volumes, after every job; never run docker compose up or down yourself",
    "use docker compose exec -T <service> ... in setup and jobs; -T is required, and no -f "
    "or -p: the project is already selected",
    "published ports move: read MULEBOX_PORT_<SERVICE>_<PORT> or use it in env:, never a "
    "port number from a compose file; the address is 127.0.0.1",
    "the build machine's job_env reaches services; a value the service sets itself wins",
    "services get 65536 open files unless they set ulimits.nofile",
)
CACHES = (
    "needs: [cache-pnpm, cache-composer, cache-npm, cache-pip] turns package caches on; a "
    "container sees a cache only if the compose file mounts ${MULEBOX_CACHE_PNPM}, "
    "${MULEBOX_CACHE_COMPOSER}, ${MULEBOX_CACHE_NPM} or ${MULEBOX_CACHE_PIP}",
    "to replace an external cache volume, mount the cache on the same container path in a "
    "CI-only compose file; external volumes stay refused",
    "mount the pnpm store at the same path as on the machine, or pnpm may recreate node_modules "
    "and install again",
    "a service with a cache runs as root or ${UID}:${GID}",
    "every branch of a project on a machine shares its cache; clearing it is a person's job on "
    "the build machine: ask, and do not ssh in",
)
JOB_STAGES = (
    f"a job goes through stages: {', '.join(STAGES)}; mulebox status shows steps and usual",
    "usual is what past passed runs took, not progress: never turn it into a percentage",
    "image pull progress is summarised, so a quiet log during a pull is normal",
    f"logs expire after {DEFAULT_LOG_DAYS} days by default; the job and its stages remain",
)
EVENTS = (
    "mulebox events prints one JSON line per state change and no log; it exits when the job "
    "ends, with the job's exit code, and survives a dropped connection",
    "every line has v, event, job_id and state; ignore events and keys you do not know",
    "queued has position, waiting_for, running_ahead (the jobs on the machines now), "
    "branch_busy (the job holding this branch, which it waits for even with a free slot) and "
    "estimate_s (how long this job usually runs, from "
    "its past runs; null when unknown; an estimate, not a promise, and not the time in line); "
    "started has machine; finished has outcome, exit_code and duration_s",
    "finished also has stage, where a job that ended badly failed (null when not known), and "
    "stop_reason when its outcome is stopped",
    "stage comes as a job enters a stage, with stage, number and started_at",
    "check_in comes every timeout_min of a running job, with elapsed_s, stage, output_idle_s, "
    "last_line (the job's last output, redacted), idle_s, job_cpu_pct, cpu_pct and net_kib_s; "
    "a reading it could not measure is null",
    "after finished, read mulebox logs <job-id> --summary if the job failed",
)
TIME_LIMITS = (
    "no job has a time limit: a job that is working finishes, however long it takes, whether "
    "anyone is there or not",
    "every timeout_min a running job asks if all is well: a check_in event with elapsed time, "
    "stage, seconds since the last output, the job's CPU, and the machine's CPU and network",
    "answer it: mulebox ok <job-id> if it is fine, mulebox cancel <job-id> if it is not",
    "a job is stopped only when it is stuck: its question has gone unanswered for one more "
    "timeout_min, and it has had no output, CPU or service traffic of its own for that long, "
    "or 15 minutes if that is shorter",
    "a job the machine cannot measure stops only after 24 hours with its question unanswered",
    "a queued job is never stopped, and a job goes on if its client goes away; Ctrl-C and "
    "mulebox cancel stop it",
    "a stopped job shows stopped: stuck and exits 76: it says nothing about the code",
    "mulebox status shows the activity and any waiting question at any time",
    "any mulebox command in the project prints waiting questions and the results of jobs that "
    "finished while you were away, on stderr; --json stays clean; mulebox contract does not, as "
    "it needs no network",
)
WAYS_TO_WAIT = (
    "follow: mulebox check, attached, or mulebox events --job <job-id> --json",
    "be pinged when it ends: mulebox check --detach, then mulebox wait <job-id> as a background "
    "command",
    "check later: mulebox check --detach, then mulebox status <job-id>; your next mulebox "
    "command in the project also tells you the result",
)
RULES = (
    "if mulebox is unreachable, stop and tell the user; never run heavy commands locally",
    "if this contract's schema is higher than the one your mulebox skill says it was written "
    "for, tell the user the skill is behind and that mulebox skill update fixes it; never "
    "update the skill yourself",
    "a detached job keeps running without you: cancel it with mulebox cancel if you no longer "
    "want it",
    "a check-in is a question to you: look at the activity, then answer with mulebox ok or "
    "mulebox cancel",
    "mulebox check does not repeat itself: on the same files and settings it gives the earlier "
    "result of the last 24 hours, or joins the same job if it is running; a result from while "
    "you were away counts, so do not retest; --again forces a run. A failure from before a "
    "mulebox upgrade does not count and runs again",
    "run mulebox doctor before a project's first job, and after changing toolchain, needs or "
    "compose files: it finds what a job would fail on, before anything is uploaded; it exits "
    "1 if a job would not run, and warnings alone exit 0",
    "a failed job ends with a short summary on stderr: read it first, and the full log only "
    "if it is not enough",
    "old logs expire on the build machine: mulebox logs says so, and mulebox status still has "
    "the result",
    "do not ssh into the build machine to change, install or delete things",
    "the coordinator and the workers must be upgraded together: if mulebox doctor reports "
    "different versions, tell the user",
    "put no real secrets, hosts or personal paths in .mulebox.yml or workflows",
    "a database a job shares with anything else must have ${MULEBOX_JOB_SLUG} in its name, and "
    "never use an existing database; a database in a compose service of the job itself is that "
    "job's alone, so its name is free",
    "waiting in the queue is normal; do not cancel and resubmit to speed it up; if the wait "
    "may be long, run the job detached",
    "do not cancel other people's jobs",
    "a pinned toolchain version installs itself the first time a job needs it, which can take "
    "minutes; if that fails the job exits 5 and lists the versions the machine has: switch to one "
    "only if it matches the project, otherwise tell the user why the install failed",
    "show the user a feedback draft and get their approval before mulebox feedback post",
)


def _settings(config: ProjectConfig) -> dict[str, dict[str, Any]]:
    """What a job does differently from the top-level defaults, per job that has any."""
    out: dict[str, dict[str, Any]] = {}
    for name in config.job_options:
        job, _ = for_job(config, name)
        out[name] = {"setup": job.setup, "install": job.install,
                     "compose": bool(job.compose),
                     "ports": [port_variable(port) for port in job.host_ports]}
    return out


def _project(config: ProjectConfig) -> dict[str, Any]:
    return {"name": config.project, "jobs": dict(config.jobs), "full_gate": FULL_GATE,
            "job_settings": _settings(config),
            "setup": config.setup, "install": config.install,
            "toolchain": dict(config.toolchain),
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
        "caches": list(CACHES), "stages": list(JOB_STAGES), "time_limits": list(TIME_LIMITS),
        "exit_codes": [{"code": code, "meaning": meaning, "action": action}
                       for code, meaning, action in EXIT_CODES],
        "rules": list(RULES),
    }


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def _setting_text(project: dict[str, Any], name: str) -> str:
    settings = project["job_settings"].get(name)
    if settings is None:
        return ""
    setup = settings["setup"] or "none"
    containers = "" if settings["compose"] or not project["compose"] else ", no containers"
    ports = "".join(f", port ${variable}" for variable in settings["ports"])
    return f" (setup: {setup}{containers}{ports})"


def _project_text(project: dict[str, Any] | None) -> list[str]:
    if project is None:
        return ["No .mulebox.yml here: this project is not set up for mulebox yet.",
                "Setup steps: mulebox's docs/agents.md, section 2."]
    lines = [f"Project: {project['name']} (check-in every {project['timeout_min']} min)"]
    if project["install"]:
        lines.append(f"Install, only when what it depends on changed: {project['install']}")
    if project["setup"]:
        lines.append(f"Setup before a job, skipped while nothing it depends on changed: "
                     f"{project['setup']}")
    lines += ["", "Jobs:"]
    for name, command in project["jobs"].items():
        run = "mulebox check" if name == FULL_GATE else f"mulebox check {name}"
        lines.append(f"- {run}: {command}{_setting_text(project, name)}")
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
              "", "Package caches:", *_bullets(contract["caches"]),
              "", "Stages:", *_bullets(contract["stages"]),
              "", "Time limits:", *_bullets(contract["time_limits"]),
              "", "Never uploaded:",
              ", ".join(contract["never_uploaded"]), "",
              "Exit codes (otherwise the job's own code):"]
    lines += [f"- {e['code']}: {e['meaning']}. {e['action']}." for e in contract["exit_codes"]]
    lines += ["", "Rules:", *_bullets(contract["rules"])]
    return "\n".join(lines) + "\n"
