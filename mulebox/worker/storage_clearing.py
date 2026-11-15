"""Carrying out a sweep's plan (worker/storage_sweep.py): removing the folders planned to go
and slimming those planned to slim (slim.py). Both stop the node's claims while they run, and
skip a folder a job of this node took meanwhile. Split from storage_sweep.py; `Agent` provides
`node`, `paths` and `_in_use`.
"""

from __future__ import annotations

import time
from typing import Any

from mulebox.common.log import get_logger
from mulebox.worker import project_disk, project_work, slim, storage_rules

LOG = get_logger("worker.storage")
SETTLE_S = 1.0  # after claims stop, for a claim already on its way to land in `active`


class Clearing:
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

    def _slim(self, planned: list[storage_rules.Folder], state: dict[str, Any],
              errors: list[str]) -> list[storage_rules.Folder]:
        """Slim the folders planned (slim.py), each unless a job took it meanwhile."""
        state["removing"] = True
        time.sleep(SETTLE_S)
        reclaim = project_work._reclaimer(self.node, self.paths)
        done = []
        for folder in planned:
            running, unsure = self._in_use()
            if (folder.project, folder.folder) in running or folder.project in unsure:
                continue
            try:
                slim.slim(self.paths, folder.project, folder.folder, reclaim)
            except Exception as exc:  # noqa: BLE001 - one folder must not stop the rest
                LOG.warning("could not slim %s/%s: %s", folder.project, folder.folder, exc)
                errors.append(f"slim {folder.project}/{folder.folder}: {exc}"[:300])
                continue
            LOG.info("slimmed %s/%s, %d bytes", folder.project, folder.folder, folder.frees or 0)
            folder.size = max(0, folder.size - (folder.frees or 0))
            folder.slim = storage_rules.DONE
            done.append(folder)
        state["removing"] = False
        return done

