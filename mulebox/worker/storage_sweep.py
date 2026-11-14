"""The worker keeps its disk in check on its own (design.md, Project folders, Disk use and cleanup
on its own). Split from agent.py: `Agent` provides `node`, `paths`, `docker`, `active`,
`finishing`, `clock` and the project orders (orders.py).

- **When**: a minute after the worker starts, then every hour; and within a minute when the
  disk's free space falls under the node's `keep_free`, at most every `LOW_EVERY_S`.
- **What**: in a thread of its own, it measures mulebox's folders (storage_scan.py), plans each
  branch folder's fate (storage_rules.py) and removes those planned, through the same removal as
  `mulebox project clean`. The node claims no job while it removes, and it skips any folder a
  job of this node uses by then.
- **The report** of the last sweep goes with the next claim or heartbeat as `storage`, once;
  the coordinator keeps it for `mulebox storage` and the dashboard. The user's keep marks come
  back in every reply as `storage_keeps`.
"""

from __future__ import annotations

import shutil
import threading
import time
from typing import Any

from mulebox.common.log import get_logger
from mulebox.worker import project_disk, project_home, project_work, storage_rules, storage_scan

LOG = get_logger("worker.storage")
FIRST_AFTER_S = 60.0
EVERY_S = 3600.0
LOW_CHECK_S = 60.0  # how often free space is looked at, a cheap call
LOW_EVERY_S = 600.0  # the least time between sweeps started for low space
SETTLE_S = 1.0  # after claims stop, for a claim already on its way to land in `active`


class Storing:
    def _store(self) -> dict[str, Any]:
        if not hasattr(self, "_storage"):
            self._storage = {"keeps": set(), "report": None, "offered": None, "sent": None,
                             "thread": None, "removing": False, "last": None,
                             "next": time.time() + FIRST_AFTER_S, "low_check": 0.0}
        return self._storage

    # -- what goes out and comes back with claims and heartbeats -----------------------
    def _storage_fields(self) -> dict[str, Any]:
        """`{"storage": report}` while the last report has not gone out yet."""
        state = self._store()
        report = state["report"]
        if report is None or report["at"] == state["sent"]:
            return {}
        state["offered"] = report["at"]
        return {"storage": report}

    def _take_replies(self, reply: dict[str, Any] | None) -> None:
        """A coordinator's reply: its project orders, the user's keep marks, and that the report
        offered with the call arrived."""
        self._take_orders(reply or {})
        if reply is None:
            return
        state = self._store()
        state["sent"] = state["offered"]
        keeps = reply.get("storage_keeps")
        if isinstance(keeps, list):
            state["keeps"] = {(k.get("project"), k.get("branch")) for k in keeps
                              if isinstance(k, dict) and isinstance(k.get("project"), str)}

    # -- the sweep ---------------------------------------------------------------------
    def _housekeeping(self, now: float) -> bool:
        """Start a sweep when one is due; True while orders run or a sweep removes folders,
        when the node claims no job."""
        state = self._store()
        busy = self._ordering(now)
        thread = state["thread"]
        if thread is not None and not thread.is_alive():
            state["thread"] = thread = None
        if thread is None and self._sweep_due(state):
            state["thread"] = threading.Thread(target=self._sweep, daemon=True,
                                               name="mulebox-storage")
            state["thread"].start()
        return busy or state["removing"]

    def _sweep_due(self, state: dict[str, Any]) -> bool:
        wall = time.time()
        if wall >= state["next"]:
            return True
        if wall - state["low_check"] < LOW_CHECK_S:
            return False
        state["low_check"] = wall
        if state["last"] is not None and wall - state["last"] < LOW_EVERY_S:
            return False
        usage = shutil.disk_usage(self.paths.projects if self.paths.projects.is_dir()
                                  else self.paths.jobs)
        return usage.free < self.node.storage.reserve(usage.total)

    def _in_use(self) -> tuple[set[tuple[str, str]], set[str]]:
        """(project, folder) pairs jobs of this node use, and projects whose job has no folder
        yet, whose folders all count as in use until it has."""
        folders, unsure = set(), set()
        for job in [*self.active.values(), *self.finishing]:
            if job.tree is not None:
                folders.add((job.project, job.tree.name))
            elif job.branch is not None:
                folders.add((job.project, project_home.slug(job.branch)))
            else:
                unsure.add(job.project)
        return folders, unsure

    def _keep_set(self) -> set[tuple[str, str | None]]:
        return {(project, None if branch is None else project_home.slug(branch))
                for project, branch in self._store()["keeps"]}

    def _sweep(self) -> None:
        state = self._store()
        try:
            state["report"] = self._swept(state)
        except Exception:  # noqa: BLE001 - a sweep must never stop the worker
            LOG.exception("storage sweep failed")
        finally:
            state["removing"] = False
            state["last"] = time.time()
            state["next"] = state["last"] + EVERY_S

    def _swept(self, state: dict[str, Any]) -> dict[str, Any]:
        policy = self.node.storage
        folders, held = storage_scan.measure(self.paths)
        disk = storage_scan.disk(self.paths)
        reserve = policy.reserve(disk["total"])
        running, unsure = self._in_use()
        plan = storage_rules.plan(
            folders, policy, time.time(), self._keep_set(),
            running | {(f.project, f.folder) for f in folders if f.project in unsure},
            disk["free"], reserve)
        removed = self._remove(plan.to_remove, state) if plan.to_remove else []
        if removed:
            disk = storage_scan.disk(self.paths)
        return _report(plan, removed, held, disk, reserve, policy.report(),
                       storage_scan.docker(self.docker))

    def _remove(self, planned: list[storage_rules.Folder], state: dict[str, Any]
                ) -> list[storage_rules.Folder]:
        state["removing"] = True  # the loop claims nothing from its next step on
        time.sleep(SETTLE_S)
        reclaim = project_work._reclaimer(self.node, self.paths)
        done = []
        for folder in planned:
            running, unsure = self._in_use()
            if (folder.project, folder.folder) in running or folder.project in unsure:
                folder.fate = storage_rules.RUNNING
                continue
            try:
                project_disk.remove_worktree(self.paths, folder.project, folder.folder, reclaim)
            except Exception as exc:  # noqa: BLE001 - one folder must not stop the rest
                LOG.warning("could not remove %s/%s: %s", folder.project, folder.folder, exc)
                folder.fate = storage_rules.STAYS
                continue
            LOG.info("removed %s/%s, %d bytes, unused", folder.project, folder.folder, folder.size)
            done.append(folder)
        state["removing"] = False
        return done


def _report(plan: storage_rules.Plan, removed: list[storage_rules.Folder], held: dict[str, Any],
            disk: dict[str, int], reserve: int, policy: dict[str, Any],
            docker: dict[str, Any] | None) -> dict[str, Any]:
    gone = {(f.project, f.folder) for f in removed}
    projects: dict[str, dict[str, Any]] = {
        name: {"project": name, **sizes, "folders": []} for name, sizes in held["projects"].items()}
    for folder in plan.folders:
        if (folder.project, folder.folder) in gone:
            continue
        projects.setdefault(folder.project, {"project": folder.project, "home": 0, "caches": 0,
                                             "folders": []})["folders"].append(
            {"folder": folder.folder, "size": folder.size, "last_used": folder.last_used,
             "fate": folder.fate, "removed_in": folder.removed_in})
    return {"at": time.time(), "disk": {**disk, "reserve": reserve}, "policy": policy,
            "projects": sorted(projects.values(), key=lambda p: p["project"]),
            "shared": held["shared"], "docker": docker, "idle": plan.idle, "short": plan.short,
            "removed": {"count": len(removed), "bytes": sum(f.size for f in removed)}}
