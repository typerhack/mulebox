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
- **Re-planned between sweeps**: when the gone branches or the keep marks change, and every
  `REPLAN_EVERY_S`, the plan is made again on the last measurement (sizes are not measured
  again, last jobs and free space are), so what the report says goes next is what a sweep
  would remove now, not what it would have at the last measurement.
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
REPLAN_EVERY_S = 900.0  # the plan on the last measurement is made again at least this often


class Storing:
    def _store(self) -> dict[str, Any]:
        if not hasattr(self, "_storage"):
            self._storage = {"keeps": set(), "gone": set(), "report": None, "offered": None,
                             "sent": None, "thread": None, "removing": False, "last": None,
                             "next": time.time() + FIRST_AFTER_S, "low_check": 0.0,
                             "first": True, "lock": threading.Lock(), "measured": None,
                             "replan": False}
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
            keeps = {(k.get("project"), k.get("branch")) for k in keeps
                     if isinstance(k, dict) and isinstance(k.get("project"), str)}
            state["replan"] |= keeps != state["keeps"]
            state["keeps"] = keeps
        gone = reply.get("storage_gone")
        if isinstance(gone, dict):
            gone = {(project, slug(branch)) for project, names in gone.items()
                    if isinstance(names, list) for branch in names if isinstance(branch, str)}
            state["replan"] |= gone != state["gone"]
            state["gone"] = gone

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
        elif thread is None and self._replan_due(state):
            state["replan"] = False
            state["thread"] = threading.Thread(target=self._replan, daemon=True,
                                               name="mulebox-storage-plan")
            state["thread"].start()
        return busy or state["removing"]

    @staticmethod
    def _replan_due(state: dict[str, Any]) -> bool:
        report = state["report"]
        return (state["measured"] is not None and report is not None
                and (state["replan"] or time.time() - report["at"] >= REPLAN_EVERY_S))

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

    def _sweep(self, trigger: str = "hourly", docker: bool | None = None,
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
        docker = order.get("docker")  # True or False as asked; none from an older sender: the setting
        record = self._sweep("now", docker if isinstance(docker, bool) else None, by_hand=True)
        if record is None:
            return 1, "mulebox: the cleanup failed; the worker's log says why"
        return 0, summary(record)

    def _swept(self, trigger: str, docker: bool | None, by_hand: bool,
               state: dict[str, Any]) -> dict[str, Any]:
        started, policy = time.time(), self.node.storage
        folders, held = storage_scan.measure(self.paths)
        disk = storage_scan.disk(self.paths)
        before, reserve = disk["free"], policy.reserve(disk["total"])
        plan = self._plan(folders, held, disk, state)
        errors: list[str] = []
        act = by_hand or policy.auto_clean
        removed = self._remove(plan.to_remove, state, errors) if act and plan.to_remove else []
        docker = bool(act and policy.docker_clean) if docker is None else docker
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
        gone = {(f.project, f.folder) for f in removed}
        state["measured"] = {"at": started, "held": held, "sweep": sweep,
                             "docker": storage_scan.docker(self.docker),
                             "folders": [f for f in folders if (f.project, f.folder) not in gone]}
        state["replan"] = False
        return self._report(plan, removed, state)

    def _plan(self, folders: list[storage_rules.Folder], held: dict[str, Any],
              disk: dict[str, int], state: dict[str, Any]) -> storage_rules.Plan:
        policy = self.node.storage
        running, unsure = self._in_use()
        plan = storage_rules.plan(
            folders, policy, time.time(), self._keep_set(),
            running | {(f.project, f.folder) for f in folders if f.project in unsure},
            disk["free"], policy.reserve(disk["total"]), state["gone"])
        return storage_rules.trim(plan, storage_report.held_total(folders, held),
                                  policy.max_bytes())

    def _report(self, plan: storage_rules.Plan, removed: list[storage_rules.Folder],
                state: dict[str, Any]) -> dict[str, Any]:
        measured, policy = state["measured"], self.node.storage
        disk = storage_scan.disk(self.paths)
        report = storage_report.build(plan, removed, measured["held"], disk,
                                      policy.reserve(disk["total"]), policy.report(),
                                      measured["docker"], storage_scan.where(self.paths),
                                      measured["sweep"])
        upcoming = state["next"] if state["next"] > time.time() else time.time() + EVERY_S
        return {**report, "measured_at": measured["at"], "next_sweep": upcoming}

    def _replan(self) -> None:
        """The plan made again on the last measurement: a folder removed since drops out, last
        jobs and free space are read again (cheap), sizes stay as measured."""
        state = self._store()
        with state["lock"]:
            try:
                measured = state["measured"]
                folders = [storage_rules.Folder(f.project, f.folder, f.size,
                                                storage_scan.last_used(self.paths, f.project, f.folder))
                           for f in measured["folders"]
                           if (self.paths.project_home(f.project) / "trees" / f.folder).is_dir()]
                measured["folders"] = folders
                disk = storage_scan.disk(self.paths)
                state["report"] = self._report(self._plan(folders, measured["held"], disk, state),
                                               [], state)
            except Exception:  # noqa: BLE001 - a plan must never stop the worker
                LOG.exception("storage plan failed")

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
