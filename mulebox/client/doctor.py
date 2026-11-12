"""What `mulebox doctor` concludes: pure, from the project and what the machine reported.

Findings are `ok`, `warn` (it may still work) or `fail` (a job would not run). A machine that
is too old to report its toolchains is a warning, not a failure: doctor does not know.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from mulebox.client.skill_install import AHEAD, BEHIND, DIFFERS, MISSING, Copy
from mulebox.common import disk, upgrade
from mulebox.common.config import XCODE, ProjectConfig
from mulebox.common.dashboard_address import place
from mulebox.common.env_rules import unknown_references
from mulebox.common.versions import compare, same_release

OK, WARN, FAIL = "ok", "warn", "fail"
TOPIC_WIDTH = 9
Worker = dict[str, Any]
Facts = dict[str, Any]  # {"version": str | None, "workers": list[Worker] | None}


@dataclass(frozen=True)
class Finding:
    level: str
    topic: str
    text: str


def env_references(project: ProjectConfig) -> list[Finding]:
    """Names in `env:` this file cannot explain. Later entries never get here: they fail to
    load. These may come from the machine's `job_env`; if not, the job cannot start."""
    return [Finding(WARN, "env", f"{key} uses ${{{name}}}, which is no earlier env: entry and no "
                    "mulebox variable; unless the machine's job_env sets it, the job cannot "
                    "start (exit 5)") for key, name in unknown_references(project.env)]


def registries(reached: dict[str, Any]) -> list[Finding]:
    """What the machine could connect to, from a `reach` reply."""
    missing = sorted(host for host, ok in reached.items() if not ok)
    if missing:
        return [Finding(WARN, "registry", f"the node cannot connect to "
                        f"{', '.join(missing)}: a job that must fetch an image from there "
                        "would not start (exit 5). Images it already has still work")]
    return [Finding(OK, "registry", f"the node can connect to {host}")
            for host in sorted(reached)]


def dashboard(facts: Facts) -> list[Finding]:
    """Where the user can watch, if the machine says."""
    found = place(facts.get("dashboard"))
    return [Finding(OK, "dashboard", found)] if found else []


def versions(client: str, facts: Facts) -> list[Finding]:
    """Client against machine, machine against its workers."""
    machine = facts.get("version")
    if not machine:
        return [Finding(WARN, "version", "the node did not say its version")]
    if machine == client:
        out = [Finding(OK, "version", f"client and node both run {client}")]
    else:
        fix = ("upgrade the dev machine: " + upgrade.command() if compare(client, machine) == -1
               else "bring the machine up with `mulebox setup <host>`")
        out = [Finding(WARN, "version", f"client {client}, node {machine}: newer "
                       f"options may be ignored or refused; {fix}")]
    for worker in facts.get("workers") or ():
        reported = worker.get("version")
        if reported and reported != machine:
            out.append(Finding(WARN, "version", f"worker {worker.get('worker')} runs {reported}, "
                               f"its coordinator {machine}; run `mulebox setup` for the "
                               "older one from a dev machine on the newer mulebox"))
    return out


def _missing(worker: Worker, project: ProjectConfig) -> list[str]:
    """What this worker lacks and no job can add."""
    offers = set(worker.get("capabilities") or ())
    return [f"capability {need}" for need in project.all_needs if need not in offers]


def _toolchain_gaps(worker: Worker, project: ProjectConfig) -> list[str]:
    """Versions a job would install first; toolchains it does not report are not counted."""
    tools = worker.get("toolchains")
    gaps = []
    for name, version in project.toolchain.items() if tools is not None else ():
        if name == XCODE:
            continue  # never installed by a job: _xcode_gap
        have = tools.get(name) or []
        if version not in have:
            gaps.append(f"{name} {version} (has {', '.join(have) or 'none'})")
    return gaps


def _xcode_gap(worker: Worker, project: ProjectConfig) -> str | None:
    """The pinned Xcode, when this Mac reports others: a job there would exit 5."""
    version, tools = project.toolchain.get(XCODE), worker.get("toolchains")
    have = (tools or {}).get(XCODE) or []
    if version is None or tools is None or any(same_release(v, version) for v in have):
        return None
    return f"{worker.get('worker')} has {', '.join(have) or 'none'}"


def _wanted(project: ProjectConfig, leaving: Sequence[str] = ()) -> str:
    """What the project needs, without what is only to be installed (`leaving`, as _toolchain_gaps
    words it): a machine does not offer what a first job has yet to fetch."""
    wanted = [*project.all_needs, *(f"{n} {v}" for n, v in project.toolchain.items())]
    kept = [item for item in wanted if not any(gap.startswith(f"{item} (") for gap in leaving)]
    return ", ".join(kept) or "nothing special"


def _fix(project: ProjectConfig) -> str:
    mac = (f"; `{XCODE}` is offered by a Mac node with Xcode installed, by itself"
           if XCODE in project.all_needs else "")
    return f"a capability goes into `capabilities` in the machine's node.toml{mac}"


def machines(project: ProjectConfig, workers: list[Worker]) -> list[Finding]:
    """Can any machine run this project?"""
    if not workers:
        return [Finding(WARN, "machine", "no node has connected to this coordinator yet, "
                        "so a job would wait; tell the user")]
    gaps = {w.get("worker"): _missing(w, project) for w in workers}
    able = [w for w in workers if not gaps[w.get("worker")]]
    if not able:
        lacking = "; ".join(f"{name} lacks {', '.join(miss)}" for name, miss in gaps.items())
        return [Finding(FAIL, "machine", f"no node can run this project: {lacking}. "
                        f"{_fix(project)}")]
    usable = [w for w in able if w.get("online")]
    to_install = sorted({gap for w in usable for gap in _toolchain_gaps(w, project)})
    if not usable:
        names = ", ".join(str(w.get("worker")) for w in able)
        return [Finding(WARN, "machine", f"only offline machines can run this project: {names}; "
                        "a job would wait for one of them")]
    unsure = [str(w.get("worker")) for w in usable if w.get("toolchains") is None]
    if unsure and project.toolchain:
        return [Finding(WARN, "machine", f"{', '.join(unsure)} did not report its toolchains (its "
                        f"mulebox is older), so {_wanted(project)} is unconfirmed")]
    xcode_gaps = [gap for w in usable if (gap := _xcode_gap(w, project)) is not None]
    if xcode_gaps and len(xcode_gaps) == len(usable):
        return [Finding(FAIL, "machine", f"Xcode {project.toolchain[XCODE]} is on no online Mac "
                        f"node ({'; '.join(xcode_gaps)}), and mulebox does not install Xcode: a "
                        "job would exit 5. Pin one of those, or install it on a Mac node")]
    names = ", ".join(str(w.get("worker")) for w in usable)
    ready = any(not _toolchain_gaps(w, project) for w in usable)
    found = [Finding(OK, "machine", f"{names} offers what this project needs: "
                     f"{_wanted(project, () if ready else to_install)}")]
    if to_install:
        found.append(Finding(OK, "machine", f"{'; '.join(to_install)}: the first job installs it, "
                             "once, which can take minutes"))
    if XCODE in project.toolchain:
        found += _xcodes(w for w in usable if _xcode_gap(w, project) is None)
    return found


def _xcodes(workers: Iterable[Worker]) -> list[Finding]:
    """Each Mac's Xcodes with their SDKs and simulator runtimes, as its worker reports them."""
    found = []
    for w in workers:
        tools = w.get("toolchains") or {}
        if tools.get(XCODE):
            found.append(Finding(OK, "xcode", f"{w.get('worker')}: Xcode "
                                 f"{', '.join(tools[XCODE])}; SDKs "
                                 f"{', '.join(tools.get('xcode-sdk') or ()) or 'none reported'}; "
                                 f"simulators {', '.join(tools.get('simulator') or ()) or 'none'}"))
    return found


def inventory(workers: list[Worker]) -> list[Finding]:
    """Outside a project: what each machine offers, with nothing to compare it to."""
    return [Finding(OK, "machine", f"{w.get('worker')} ({'online' if w.get('online') else 'offline'})"
                    f": {', '.join(w.get('capabilities') or ()) or 'no capabilities'}")
            for w in workers] + _xcodes(workers)


def disks(workers: list[Worker]) -> list[Finding]:
    return [Finding(WARN, "disk", disk.warning(str(w.get("worker")), w["disk_free"]))
            for w in workers if w.get("online") and disk.is_low(w.get("disk_free"))]


def skills(copies: list[Copy], schema: int) -> list[Finding]:
    """The agent skill in each Claude config folder; no folders, nothing to say."""
    if copies and all(copy.state == MISSING for copy in copies):
        return [Finding(OK, "skill", "not installed; `mulebox skill install` adds it")]
    out = []
    for copy in copies:
        if copy.state in (BEHIND, DIFFERS):
            written = f"schema {copy.schema}" if copy.schema else "no schema"
            out.append(Finding(WARN, "skill", f"the copy in {copy.folder} is out of date (written "
                               f"for {written}, current {schema}): run `mulebox skill update`, "
                               "then read the skill again"))
        elif copy.state == AHEAD:
            out.append(Finding(WARN, "skill", f"the copy in {copy.folder} is newer than this "
                               f"mulebox; upgrade mulebox: {upgrade.command()}"))
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
