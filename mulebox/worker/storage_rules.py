"""What the sweep does with each branch folder on this node (design.md, Project folders, Disk use
and cleanup on its own). Pure: the folders, their sizes and last jobs, the node's policy, the
user's keep marks and the folders jobs run in now go in; a plan comes out, which the sweep
(storage_sweep.py) carries out and the report (storage_scan.py) shows.

Each folder gets one fate, the first that holds:
- `running`: a job runs in it now. Never removed.
- `kept`: the user marked it, or its whole project, to keep (`mulebox project keep`).
- `remove` (`why: gone`): its branch is on no dev machine any more (`gone`, from the
  coordinator); it goes at the next sweep, latest or not.
- `latest`: the project's latest folder, with `keep_latest`.
- `remove` (`why: unused`): no job for `unused_days`; the sweep removes it.
- `stays`: used lately; `removed_in` says in how many days it would go.

Past the node's `max_size` (mulebox's own folders, caches and tools together), `trim` then
marks the oldest `stays` folders `remove` (`why: size`) until mulebox is back under it; what it
cannot reach that way (latest, kept and running folders stay) is left as `over`.

A `stays` folder with no job for `slim_hours` is slimmed (`slim: due`, worker/slim.py): what git
ignores in it goes, the checkout stays; one slimmed already says `slim: done`. Its `frees` is
what slimming gives back, measured by the sweep.

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
DONE, DUE = "done", "due"  # a folder's `slim`
HOUR = 3600.0


@dataclass
class Folder:
    project: str
    folder: str
    size: int
    last_used: float | None  # None: never seen a job here (counts as long ago)
    fate: str = STAYS
    removed_in: float | None = None  # days, for `stays`
    why: str | None = None  # for `remove`: `gone` or `unused`
    slim: str | None = None  # `done`: slimmed and no job since; `due`: slimmed at the next sweep
    frees: int | None = None  # for `due`: the bytes slimming gives back


@dataclass
class Plan:
    folders: list[Folder]
    idle: list[dict[str, Any]] = field(default_factory=list)
    short: dict[str, Any] | None = None
    over: int = 0  # bytes still over `max_size` after `trim`

    @property
    def to_remove(self) -> list[Folder]:
        return [f for f in self.folders if f.fate == REMOVE]

    @property
    def to_slim(self) -> list[Folder]:
        return [f for f in self.folders if f.fate == STAYS and f.slim == DUE]


def _is_kept(folder: Folder, keeps: set[tuple[str, str | None]]) -> bool:
    return (folder.project, None) in keeps or (folder.project, folder.folder) in keeps


def plan(folders: list[Folder], policy: StoragePolicy, now: float,
         keeps: set[tuple[str, str | None]], running: set[tuple[str, str]],
         free: int | None = None, reserve: int | None = None,
         gone: set[tuple[str, str]] = frozenset()) -> Plan:
    """`keeps`: (project, None) for a whole project or (project, folder name); `running`:
    (project, folder name) pairs a job is in now; `free` and `reserve` in bytes, to tell
    whether the removals are enough; `gone`: (project, folder name) of branches no dev machine
    has any more."""
    by_project: dict[str, list[Folder]] = {}
    for folder in folders:
        by_project.setdefault(folder.project, []).append(folder)
    out = Plan(folders)
    for project, own in sorted(by_project.items()):
        own.sort(key=lambda f: f.last_used or 0.0, reverse=True)
        live = [f for f in own if (project, f.folder) not in gone]
        newest = live[0] if live else None  # the latest is the newest folder of a live branch
        for folder in own:
            age = (now - folder.last_used) / DAY if folder.last_used else float("inf")
            if (project, folder.folder) in running:
                folder.fate = RUNNING
            elif _is_kept(folder, keeps):
                folder.fate = KEPT
            elif (project, folder.folder) in gone:
                folder.fate, folder.why = REMOVE, "gone"
            elif folder is newest and policy.keep_latest:
                folder.fate = LATEST
            elif age >= policy.unused_days:
                folder.fate, folder.why = REMOVE, "unused"
            else:
                folder.fate, folder.removed_in = STAYS, max(0.0, policy.unused_days - age)
            if folder.slim != DONE:
                idle = age * DAY / HOUR
                folder.slim = (DUE if folder.fate == STAYS and policy.slim_hours
                               and idle >= policy.slim_hours else None)
        if newest is None:
            continue
        idle_days = (now - newest.last_used) / DAY if newest.last_used else None
        if newest.fate in (LATEST, KEPT) and (idle_days is None or idle_days >= policy.idle_days):
            out.idle.append({"project": project, "days": None if idle_days is None else int(idle_days),
                             "size": sum(f.size for f in own if f.fate != REMOVE),
                             "kept": newest.fate == KEPT})
    if free is not None and reserve is not None:
        out.short = _short(out, free, reserve)
    return out


def _short(out: Plan, free: int, reserve: int) -> dict[str, Any] | None:
    """What could go next when the planned removals leave the disk under the reserve."""
    after = free + sum(f.size for f in out.to_remove) + sum(f.frees or 0 for f in out.to_slim)
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


def trim(out: Plan, held: int, limit: int | None) -> Plan:
    """Mark the oldest folders that may go for removal until mulebox's `held` bytes, less what is
    planned already, are under `limit`."""
    if limit is None:
        return out
    over = held - sum(f.size for f in out.to_remove) - limit
    for folder in sorted((f for f in out.folders if f.fate == STAYS),
                         key=lambda f: f.last_used or 0.0):
        if over <= 0:
            break
        folder.fate, folder.why, folder.removed_in = REMOVE, "size", None
        over -= folder.size
    out.over = max(0, over)
    return out
