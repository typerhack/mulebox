"""The worker keeps its disk in check on its own (design.md, Project folders, Disk use and cleanup
on its own). Split from agent.py: `Agent` provides `node`, `paths`, `docker`, `active`,
`finishing`, `clock` and the project orders (orders.py).

- **When**: a minute after the worker starts, then every hour; within a minute when the disk's
  free space falls under the node's `keep_free`, at most every `LOW_EVERY_S`; and at once when
  the user asks (`mulebox storage clean`, the dashboard's Run now: a `sweep` order, orders.py).
- **What**: in a thread of its own, it measures mulebox's folders (storage_scan.py), plans each
  branch folder's fate (storage_rules.py), with the branches no dev machine has any more as the
  coordinator sends them (`storage_gone`), and removes those planned, through the same removal
  as `mulebox project clean`. The node claims no job while it removes, and it skips any folder a
  job of this node uses by then. With `auto_clean` off it removes only when asked. Docker's
  unused build cache, dangling images and the images its jobs pulled and no longer use go too
  with `docker_clean` (docker_prune.py).
- **History**: each sweep's record (storage_report.py) goes with the report as `sweep`.
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
from mulebox.common.branch_folder import slug
from mulebox.common.units import size as shown
from mulebox.worker import (docker_prune, project_disk, project_home, project_work, storage_report,
                            storage_rules, storage_scan)

LOG = get_logger("worker.storage")
FIRST_AFTER_S = 60.0
EVERY_S = 3600.0
LOW_CHECK_S = 60.0  # how often free space is looked at, a cheap call
LOW_EVERY_S = 600.0  # the least time between sweeps started for low space
SETTLE_S = 1.0  # after claims stop, for a claim already on its way to land in `active`


class Storing:
    def _store(self) -> dict[str, Any]:
        if not hasattr(self, "_storage"):
            self._storage = {"keeps": set(), "gone": set(), "report": None, "offered": None,
                             "sent": None, "thread": None, "removing": False, "last": None,
                             "next": time.time() + FIRST_AFTER_S, "low_check": 0.0,
                             "first": True, "lock": threading.Lock()}
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
        """A coordinator's reply: its project orders, the user's keep marks, the gone branches,
        and that the report offered with the call arrived."""
        self._take_orders(reply or {})
        if reply is None:
            return
        state = self._store()
        state["sent"] = state["offered"]
        keeps = reply.get("storage_keeps")
        if isinstance(keeps, list):
            state["keeps"] = {(k.get("project"), k.get("branch")) for k in keeps
                              if isinstance(k, dict) and isinstance(k.get("project"), str)}
        gone = reply.get("storage_gone")
        if isinstance(gone, dict):
            state["gone"] = {(project, slug(branch)) for project, names in gone.items()
                             if isinstance(names, list) for branch in names
                             if isinstance(branch, str)}

    # -- the sweep ---------------------------------------------------------------------
    def _housekeeping(self, now: float) -> bool:
        """Start a sweep when one is due; True while orders run or a sweep removes folders,
        when the node claims no job."""
        state = self._store()
        busy = self._ordering(now)
        thread = state["thread"]
        if thread is not None and not thread.is_alive():
            state["thread"] = thread = None
        if thread is None and (trigger := self._sweep_due(state)):
            state["thread"] = threading.Thread(target=self._sweep, args=(trigger,), daemon=True,
                                               name="mulebox-storage")
            state["thread"].start()
        return busy or state["removing"]

    def _sweep_due(self, state: dict[str, Any]) -> str | None:
        """Why a sweep is due now (`start`, `hourly`, `low`), or None."""
        wall = time.time()
        if wall >= state["next"]:
            return "start" if state["first"] else "hourly"
        if wall - state["low_check"] < LOW_CHECK_S:
            return None
        state["low_check"] = wall
        if state["last"] is not None and wall - state["last"] < LOW_EVERY_S:
            return None
        usage = shutil.disk_usage(self.paths.projects if self.paths.projects.is_dir()
                                  else self.paths.jobs)
        return "low" if usage.free < self.node.storage.reserve(usage.total) else None

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

    def _sweep(self, trigger: str = "hourly", docker: bool = False,
               by_hand: bool = False) -> dict[str, Any] | None:
        """One sweep; its record, or None when it failed (logged)."""
        state = self._store()
        with state["lock"]:
            try:
                state["report"] = self._swept(trigger, docker, by_hand, state)
                return state["report"]["sweep"]
            except Exception:  # noqa: BLE001 - a sweep must never stop the worker
                LOG.exception("storage sweep failed")
                return None
            finally:
                state["removing"] = False
                state["first"] = False
                state["last"] = time.time()
                state["next"] = state["last"] + EVERY_S

    def _sweep_order(self, order: dict[str, Any]) -> tuple[int, str]:
        """A `sweep` order (the user's Run now): (exit code, what it says)."""
        record = self._sweep("now", order.get("docker") is True, by_hand=True)
        if record is None:
            return 1, "mulebox: the cleanup failed; the worker's log says why"
        return 0, summary(record)

    def _swept(self, trigger: str, docker: bool, by_hand: bool,
               state: dict[str, Any]) -> dict[str, Any]:
        started, policy = time.time(), self.node.storage
        folders, held = storage_scan.measure(self.paths)
        disk = storage_scan.disk(self.paths)
        before, reserve = disk["free"], policy.reserve(disk["total"])
        running, unsure = self._in_use()
        plan = storage_rules.plan(
            folders, policy, time.time(), self._keep_set(),
            running | {(f.project, f.folder) for f in folders if f.project in unsure},
            disk["free"], reserve, state["gone"])
        storage_rules.trim(plan, storage_report.held_total(folders, held), policy.max_bytes())
        errors: list[str] = []
        act = by_hand or policy.auto_clean
        removed = self._remove(plan.to_remove, state, errors) if act and plan.to_remove else []
        docker = docker or (act and policy.docker_clean)
        pruned = None
        if docker and self.docker is not None:
            try:
                pruned = docker_prune.prune(self.docker, self.paths, policy.unused_days)
            except Exception as exc:  # noqa: BLE001 - Docker must not stop the folders' cleanup
                LOG.warning("docker cleanup failed: %s", exc)
                errors.append(f"docker: {exc}"[:300])
        if pruned and pruned.get("error"):
            errors.append(pruned["error"])
        if removed or pruned:
            disk = storage_scan.disk(self.paths)
        sweep = storage_report.sweep_record(started, trigger, policy.auto_clean, removed, pruned,
                                            before, disk["free"], errors,
                                            0 if act else len(plan.to_remove))
        return storage_report.build(plan, removed, held, disk, reserve, policy.report(),
                                    storage_scan.docker(self.docker),
                                    storage_scan.where(self.paths), sweep)

    def _remove(self, planned: list[storage_rules.Folder], state: dict[str, Any],
                errors: list[str]) -> list[storage_rules.Folder]:
        state["removing"] = True  # the loop claims nothing from its next step on
        time.sleep(SETTLE_S)
        reclaim = project_work._reclaimer(self.node, self.paths)
        done = []
        for folder in planned:
            running, unsure = self._in_use()
            if (folder.project, folder.folder) in running or folder.project in unsure:
                folder.fate, folder.why = storage_rules.RUNNING, None
                continue
            try:
                project_disk.remove_worktree(self.paths, folder.project, folder.folder, reclaim)
            except Exception as exc:  # noqa: BLE001 - one folder must not stop the rest
                LOG.warning("could not remove %s/%s: %s", folder.project, folder.folder, exc)
                errors.append(f"{folder.project}/{folder.folder}: {exc}"[:300])
                folder.fate, folder.why = storage_rules.STAYS, None
                continue
            LOG.info("removed %s/%s, %d bytes, %s", folder.project, folder.folder, folder.size,
                     folder.why)
            done.append(folder)
        state["removing"] = False
        return done


def summary(record: dict[str, Any]) -> str:
    """A sweep's record in a few lines, for the user who ran it."""
    lines = [f"removed {record['count']} branch folder(s), {shown(record['bytes'])}"]
    pruned = record.get("docker")
    if pruned:
        lines.append(f"docker: build cache {shown(pruned['build_cache'])}, "
                     f"images {shown(pruned['images'])} freed"
                     + (f" ({', '.join(pruned['removed'])})" if pruned.get("removed") else ""))
    lines.append(f"free: {shown(record['free_before'])} before, {shown(record['free_after'])} "
                 "after")
    lines += [f"could not: {error}" for error in record.get("errors", [])]
    return "\n".join(lines)
