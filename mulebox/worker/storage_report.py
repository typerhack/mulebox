"""The storage report a worker sends after each sweep (worker/storage_sweep.py), and the record
of that sweep kept as the node's cleanup history (coordinator/storage_history.py)."""

from __future__ import annotations

import time
from typing import Any

from mulebox.worker import storage_rules

MAX_LISTED = 500  # removed folders named in one sweep's record


def held_total(folders: list[storage_rules.Folder], held: dict[str, Any]) -> int:
    """All mulebox holds on the node: branch folders, project homes and caches, shared folders."""
    return (sum(f.size for f in folders)
            + sum(p.get("home", 0) + p.get("caches", 0) for p in held["projects"].values())
            + sum(v for v in held["shared"].values() if isinstance(v, int)))


def sweep_record(started: float, trigger: str, auto: bool, removed: list[storage_rules.Folder],
                 docker: dict[str, Any] | None, free_before: int, free_after: int,
                 errors: list[str], would: int) -> dict[str, Any]:
    """One cleanup, for the history: when and why it ran, what it removed and what it freed."""
    return {"started": started, "seconds": round(time.time() - started, 1), "trigger": trigger,
            "auto": auto, "would_remove": would,
            "removed": [{"project": f.project, "folder": f.folder, "size": f.size, "why": f.why}
                        for f in removed[:MAX_LISTED]],
            "count": len(removed), "bytes": sum(f.size for f in removed), "docker": docker,
            "free_before": free_before, "free_after": free_after, "errors": errors[:20]}


def build(plan: storage_rules.Plan, removed: list[storage_rules.Folder], held: dict[str, Any],
          disk: dict[str, int], reserve: int, policy: dict[str, Any],
          docker: dict[str, Any] | None, where: dict[str, str],
          sweep: dict[str, Any]) -> dict[str, Any]:
    gone = {(f.project, f.folder) for f in removed}
    projects: dict[str, dict[str, Any]] = {
        name: {"project": name, **sizes, "folders": []} for name, sizes in held["projects"].items()}
    for folder in plan.folders:
        if (folder.project, folder.folder) in gone:
            continue
        projects.setdefault(folder.project, {"project": folder.project, "home": 0, "caches": 0,
                                             "folders": []})["folders"].append(
            {"folder": folder.folder, "size": folder.size, "last_used": folder.last_used,
             "fate": folder.fate, "removed_in": folder.removed_in, "why": folder.why})
    kept = [f for f in plan.folders if (f.project, f.folder) not in gone]
    return {"at": time.time(), "disk": {**disk, "reserve": reserve}, "policy": policy,
            "held": held_total(kept, held), "over": plan.over,
            "projects": sorted(projects.values(), key=lambda p: p["project"]),
            "shared": held["shared"], "paths": where, "docker": docker, "idle": plan.idle,
            "short": plan.short, "sweep": sweep,
            "removed": {"count": len(removed), "bytes": sum(f.size for f in removed)}}
