"""What the sweep does with each branch folder on this node (design.md, Project folders, Disk use
and cleanup on its own). Pure: the folders, their sizes and last jobs, the node's policy, the
user's keep marks and the folders jobs run in now go in; a plan comes out, which the sweep
(storage_sweep.py) carries out and the report (storage_scan.py) shows.

Each folder gets one fate, the first that holds:
- `running`: a job runs in it now. Never removed.
- `kept`: the user marked it, or its whole project, to keep (`mulebox project keep`).
- `latest`: the project's latest folder, with `keep_latest`.
- `remove`: no job for `unused_days`; the sweep removes it.
- `stays`: used lately; `removed_in` says in how many days it would go.

An idle project (its latest folder unused for `idle_days`) gets a suggestion, not a removal.
When the disk would still be under the reserve after the removals, `short` lists what could go
next, oldest first, until it covers the gap: the user decides on those.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mulebox.common.storage_policy import StoragePolicy

DAY = 86400.0
RUNNING, KEPT, LATEST, REMOVE, STAYS = "running", "kept", "latest", "remove", "stays"


@dataclass
class Folder:
    project: str
    folder: str
    size: int
    last_used: float | None  # None: never seen a job here (counts as long ago)
    fate: str = STAYS
    removed_in: float | None = None  # days, for `stays`


@dataclass
class Plan:
    folders: list[Folder]
    idle: list[dict[str, Any]] = field(default_factory=list)
    short: dict[str, Any] | None = None

    @property
    def to_remove(self) -> list[Folder]:
        return [f for f in self.folders if f.fate == REMOVE]


def _is_kept(folder: Folder, keeps: set[tuple[str, str | None]]) -> bool:
    return (folder.project, None) in keeps or (folder.project, folder.folder) in keeps


def plan(folders: list[Folder], policy: StoragePolicy, now: float,
         keeps: set[tuple[str, str | None]], running: set[tuple[str, str]],
         free: int | None = None, reserve: int | None = None) -> Plan:
    """`keeps`: (project, None) for a whole project or (project, folder name); `running`:
    (project, folder name) pairs a job is in now; `free` and `reserve` in bytes, to tell
    whether the removals are enough."""
    by_project: dict[str, list[Folder]] = {}
    for folder in folders:
        by_project.setdefault(folder.project, []).append(folder)
    out = Plan(folders)
    for project, own in sorted(by_project.items()):
        own.sort(key=lambda f: f.last_used or 0.0, reverse=True)
        for index, folder in enumerate(own):
            age = (now - folder.last_used) / DAY if folder.last_used else float("inf")
            if (project, folder.folder) in running:
                folder.fate = RUNNING
            elif _is_kept(folder, keeps):
                folder.fate = KEPT
            elif index == 0 and policy.keep_latest:
                folder.fate = LATEST
            elif age >= policy.unused_days:
                folder.fate = REMOVE
            else:
                folder.fate, folder.removed_in = STAYS, max(0.0, policy.unused_days - age)
        latest = own[0]
        idle_days = (now - latest.last_used) / DAY if latest.last_used else None
        if latest.fate in (LATEST, KEPT) and (idle_days is None or idle_days >= policy.idle_days):
            out.idle.append({"project": project, "days": None if idle_days is None else int(idle_days),
                             "size": sum(f.size for f in own if f.fate != REMOVE),
                             "kept": latest.fate == KEPT})
    if free is not None and reserve is not None:
        out.short = _short(out, free, reserve)
    return out


def _short(out: Plan, free: int, reserve: int) -> dict[str, Any] | None:
    """What could go next when the planned removals leave the disk under the reserve."""
    after = free + sum(f.size for f in out.to_remove)
    if after >= reserve:
        return None
    need = reserve - after
    rest = sorted((f for f in out.folders if f.fate in (STAYS, LATEST, KEPT)),
                  key=lambda f: f.last_used or 0.0)
    could, total = [], 0
    for folder in rest:
        if total >= need:
            break
        could.append({"project": folder.project, "folder": folder.folder, "size": folder.size,
                      "last_used": folder.last_used, "fate": folder.fate})
        total += folder.size
    return {"need": need, "could_free": total, "folders": could}
