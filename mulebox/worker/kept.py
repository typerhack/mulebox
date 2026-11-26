"""Failed jobs this worker keeps for a rerun (docs/design.md, Rerun from the failed stage).

A compose job whose command, `setup` or `install` failed keeps its Compose project, network,
ports, generated compose file and job folder for `keep_failed_min` minutes, holding no slot.
`mulebox check --from-stage` takes them over: the new job's claim names the kept job in
`reuses`, and from then on what was kept is the new job's, under the labels, folder and ports
of the job that made it (`home`), until a cleanup removes it. Kept jobs live in memory only: a
worker restart leaves them to the startup sweep, which removes them like any leftover.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mulebox.common import compose
from mulebox.common.protocol import Outcome
from mulebox.common.status import COMMAND, INSTALL, SETUP
from mulebox.worker.docker import Docker, DockerError

KEEPABLE_STAGES = (INSTALL, SETUP, COMMAND)  # the stages that run with the containers up
NOT_KEPT_EXITS = (5, 75, 76)  # could not start, interrupted, stopped stuck
CHECK_TIMEOUT_S = 15.0
_EXITED = re.compile(r"^Exited \((\d+)\)")


@dataclass
class Kept:
    job_id: str  # the failed job that holds it now
    home: str  # the job whose labels, folder and ports it carries
    project: str
    branch: str | None
    until: float  # agent clock
    key: str  # what the skipped stages depend on (rerun.py)
    env: dict[str, str] = field(default_factory=dict)  # COMPOSE_FILE, its project, the ports
    tree: Path | None = None
    memory: int = 0  # bytes its containers held, as the job's meter last read them


def keepable(outcome: Outcome | None, exit_code: int | None, stage: str | None,
             compose_job: bool, isolated: bool) -> bool:
    """Whether a job that ended so leaves something worth keeping. An isolated job keeps
    nothing yet: its door and port forward are made for one job's container."""
    if not compose_job or isolated or outcome not in (Outcome.FAILED, Outcome.TIMED_OUT):
        return False
    if exit_code is None or exit_code == 0 or exit_code in NOT_KEPT_EXITS:
        return False
    return stage in KEEPABLE_STAGES


def compose_env(env: dict[str, str]) -> dict[str, str]:
    """What of a job's environment a rerun needs again: its compose file and project, and the
    ports its services were given."""
    names = ("COMPOSE_FILE", "COMPOSE_PROJECT_NAME")
    return {k: v for k, v in env.items() if k in names or k.startswith("MULEBOX_PORT_")}


class KeptJobs:
    def __init__(self) -> None:
        self.jobs: dict[str, Kept] = {}  # by the job that holds it now

    def keep(self, kept: Kept, most: int) -> list[Kept]:
        """Keep `kept`; what must go to stay at `most`, the oldest first."""
        self.jobs[kept.job_id] = kept
        extra = sorted(self.jobs.values(), key=lambda k: k.until)[:max(0, len(self.jobs) - most)]
        for gone in extra:
            self.jobs.pop(gone.job_id, None)
        return extra

    def take(self, job_id: str) -> Kept | None:
        return self.jobs.pop(job_id, None)

    def of_branch(self, project: str, branch: str | None) -> list[Kept]:
        """What a job of this branch that takes nothing over must remove first: it gets the
        branch's folder, which the kept containers still mount."""
        found = [k for k in self.jobs.values() if k.project == project and k.branch == branch]
        for gone in found:
            self.jobs.pop(gone.job_id, None)
        return found

    def due(self, now: float) -> list[Kept]:
        found = [k for k in self.jobs.values() if k.until <= now]
        for gone in found:
            self.jobs.pop(gone.job_id, None)
        return found

    def every(self) -> list[Kept]:
        found = list(self.jobs.values())
        self.jobs.clear()
        return found

    def report(self, now: float) -> list[dict[str, Any]]:
        """`kept` for a claim or heartbeat (coordinator/kept.py)."""
        return [{"job_id": k.job_id, "left_s": round(max(0.0, k.until - now), 1),
                 "memory": k.memory} for k in self.jobs.values() if k.until > now]


def stopped(docker: Docker, home: str) -> str | None:
    """Why the kept containers cannot be used again, or None when all run (a one-shot service
    that exited 0 counts as done, as `depends_on` lets it)."""
    try:
        text = docker.run("ps", "-a", "--filter", compose.project_filter(home), "--format",
                          "{{.Names}}\t{{.Status}}", timeout_s=CHECK_TIMEOUT_S)
    except DockerError as exc:
        return f"Docker did not list them: {exc}"
    lines = [line.split("\t", 1) for line in text.splitlines() if "\t" in line]
    if not lines:
        return "its containers are gone"
    for name, status in lines:
        exited = _EXITED.match(status)
        if not status.startswith("Up") and not (exited and exited.group(1) == "0"):
            return f"container {name} is not running ({status})"
    return None
