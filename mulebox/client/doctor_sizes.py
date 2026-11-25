"""`mulebox doctor` on job sizes: a declared `size:` set beside what the job really used
(docs/design.md, Job sizes; `mulebox usage`).

A warning, never a failure: the size only decides placement. Two cases, from a job's last passed
runs once `MIN_RUNS` were measured:
- it used more than it asks (its busiest peak above the size): it slows its neighbours;
- it asks for over `TOO_MUCH` times its busiest peak: it holds room other jobs could use.
"""

from __future__ import annotations

from typing import Any

from mulebox.common import config_jobs, job_size, units
from mulebox.common.config import ProjectConfig
from mulebox.client.doctor import WARN, Finding

MIN_RUNS = 3
TOO_MUCH = 2.0


def _one(name: str, size: dict[str, float], found: dict[str, Any]) -> list[str]:
    said = []
    peak = {"cores": (found.get("cores") or {}).get("max"),
            "memory": (found.get("memory") or {}).get("max")}
    show = {"cores": lambda v: f"{v:.1f} cores", "memory": units.size}
    for part in ("cores", "memory"):
        if part not in size or peak[part] is None:
            continue
        if peak[part] > size[part]:
            said.append(f"`{name}` asks for {show[part](size[part])} but used up to "
                        f"{show[part](peak[part])}, which slows the jobs beside it")
        elif size[part] > TOO_MUCH * max(peak[part], 1e-9):
            said.append(f"`{name}` asks for {show[part](size[part])} but used at most "
                        f"{show[part](peak[part])}, which keeps room other jobs could use")
    return said


def findings(project: ProjectConfig, usage: dict[str, Any] | None) -> list[Finding]:
    """Warnings for the project's sized jobs; `usage`: a `usage` reply for the project."""
    if not usage:
        return []
    measured = {row["job"]: row for row in usage.get("jobs") or []
                if row.get("kind") == "job" and row.get("measured", 0) >= MIN_RUNS}
    out = []
    for name in project.jobs:
        size = config_jobs.for_job(project, name)[0].size
        if size and name in measured:
            fit = measured[name].get("fits") or {}
            for text in _one(name, size, measured[name]):
                tip = job_size.words({k: v for k, v in fit.items() if v is not None})
                out.append(Finding(WARN, "size", f"{text}; its last runs fit {tip} "
                                                 "(`mulebox usage --project "
                                                 f"{project.project} --job {name}`)"))
    return out
