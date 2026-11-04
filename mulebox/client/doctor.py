"""What `mulebox doctor` concludes: pure, from the project and what the machine reported.

Findings are `ok`, `warn` (it may still work) or `fail` (a job would not run). A machine that
is too old to report its toolchains is a warning, not a failure: doctor does not know.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from mulebox.client.skill_install import AHEAD, BEHIND, DIFFERS, MISSING, Copy
from mulebox.common.config import ProjectConfig

OK, WARN, FAIL = "ok", "warn", "fail"
TOPIC_WIDTH = 9
Worker = dict[str, Any]
Facts = dict[str, Any]  # {"version": str | None, "workers": list[Worker] | None}


@dataclass(frozen=True)
class Finding:
    level: str
    topic: str
    text: str


def versions(client: str, facts: Facts) -> list[Finding]:
    """Client against machine, machine against its workers."""
    machine = facts.get("version")
    if not machine:
        return [Finding(WARN, "version", "the build machine did not say its version")]
    if machine == client:
        out = [Finding(OK, "version", f"client and build machine both run {client}")]
    else:
        out = [Finding(WARN, "version", f"client {client}, build machine {machine}: newer "
                       "options may be ignored or refused; upgrade the older side")]
    for worker in facts.get("workers") or ():
        reported = worker.get("version")
        if reported and reported != machine:
            out.append(Finding(WARN, "version", f"worker {worker.get('worker')} runs {reported}, "
                               f"its coordinator {machine}; upgrade the older side"))
    return out


def _missing(worker: Worker, project: ProjectConfig) -> list[str]:
    """What this worker lacks; toolchains it does not report are not counted."""
    offers = set(worker.get("capabilities") or ())
    gaps = [f"capability {need}" for need in project.all_needs if need not in offers]
    tools = worker.get("toolchains")
    for name, version in project.toolchain.items() if tools is not None else ():
        have = tools.get(name) or []
        if version not in have:
            gaps.append(f"{name} {version} (has {', '.join(have) or 'none'})")
    return gaps


def _wanted(project: ProjectConfig) -> str:
    wanted = [*project.all_needs, *(f"{n} {v}" for n, v in project.toolchain.items())]
    return ", ".join(wanted) or "nothing special"


def _fix(project: ProjectConfig) -> str:
    tools = "; ".join(f"mulebox toolchain install {n} {v}" for n, v in project.toolchain.items())
    if tools:
        return (f"use a listed version if it matches the project, or ask a person to run: {tools}"
                "; a capability goes into `capabilities` in the machine's node.toml")
    return "a capability goes into `capabilities` in the machine's node.toml"


def machines(project: ProjectConfig, workers: list[Worker]) -> list[Finding]:
    """Can any machine run this project?"""
    if not workers:
        return [Finding(WARN, "machine", "no build machine has connected to this coordinator yet, "
                        "so a job would wait; tell the user")]
    gaps = {w.get("worker"): _missing(w, project) for w in workers}
    able = [w for w in workers if not gaps[w.get("worker")]]
    if not able:
        lacking = "; ".join(f"{name} lacks {', '.join(miss)}" for name, miss in gaps.items())
        return [Finding(FAIL, "machine", f"no build machine can run this project: {lacking}. "
                        f"{_fix(project)}")]
    usable = [w for w in able if w.get("online")]
    if not usable:
        names = ", ".join(str(w.get("worker")) for w in able)
        return [Finding(WARN, "machine", f"only offline machines can run this project: {names}; "
                        "a job would wait for one of them")]
    unsure = [str(w.get("worker")) for w in usable if w.get("toolchains") is None]
    if unsure and project.toolchain:
        return [Finding(WARN, "machine", f"{', '.join(unsure)} did not report its toolchains (its "
                        f"mulebox is older), so {_wanted(project)} is unconfirmed")]
    names = ", ".join(str(w.get("worker")) for w in usable)
    return [Finding(OK, "machine", f"{names} offers what this project needs: {_wanted(project)}")]


def inventory(workers: list[Worker]) -> list[Finding]:
    """Outside a project: what each machine offers, with nothing to compare it to."""
    return [Finding(OK, "machine", f"{w.get('worker')} ({'online' if w.get('online') else 'offline'})"
                    f": {', '.join(w.get('capabilities') or ()) or 'no capabilities'}")
            for w in workers]


def skills(copies: list[Copy], schema: int) -> list[Finding]:
    """The agent skill in each Claude config folder; no folders, nothing to say."""
    if copies and all(copy.state == MISSING for copy in copies):
        return [Finding(OK, "skill", "not installed; `mulebox skill install` adds it")]
    out = []
    for copy in copies:
        if copy.state in (BEHIND, DIFFERS):
            written = f"schema {copy.schema}" if copy.schema else "no schema"
            out.append(Finding(WARN, "skill", f"the copy in {copy.folder} is out of date (written "
                               f"for {written}, current {schema}): tell the user that "
                               "`mulebox skill update` fixes it; do not update it yourself"))
        elif copy.state == AHEAD:
            out.append(Finding(WARN, "skill", f"the copy in {copy.folder} is newer than this "
                               "mulebox; upgrade mulebox"))
        elif copy.state != MISSING:
            out.append(Finding(OK, "skill", f"{copy.state} in {copy.folder}"))
    return out


def worst(findings: list[Finding]) -> str:
    levels = {finding.level for finding in findings}
    return FAIL if FAIL in levels else WARN if WARN in levels else OK


def render(findings: list[Finding]) -> str:
    lines = [f"{f.level:<4}  {f.topic:<{TOPIC_WIDTH}} {f.text}" for f in findings]
    return "\n".join(lines) + "\n"


def as_json(findings: list[Finding]) -> dict[str, Any]:
    return {"result": worst(findings), "findings": [asdict(f) for f in findings]}
