"""What mulebox holds on this node, measured (design.md, Project folders, Disk use and cleanup on
its own). Slow on a big node (millions of files), so the sweep (storage_sweep.py) runs it in a
thread of its own, never on a request.

- Sizes as `du` counts them, a file hard-linked in several folders (pnpm's store in every
  `node_modules`) once across all of mulebox's folders (common/tree_size.py).
- A branch folder's last job: every job commits in its folder (project_home.prepare), so git's
  log of the folder's branch is written then; folders from before this have it too.
- Docker's own totals from `docker system df`: what Docker holds on the machine, not only
  mulebox's, said as such.
"""

from __future__ import annotations

import json
import re
import shutil
from typing import Any

from mulebox.common.tree_size import sizes
from mulebox.worker import project_disk, slim
from mulebox.worker.docker import Docker, DockerError
from mulebox.worker.paths import NodePaths
from mulebox.worker.storage_rules import DONE, Folder

DOCKER_TIMEOUT_S = 30.0
_DOCKER_SIZE = re.compile(r"^\s*([\d.]+)\s*([kKMGT]?B)")
_UNITS = {"B": 1, "kB": 10**3, "KB": 10**3, "MB": 10**6, "GB": 10**9, "TB": 10**12}


def last_used(paths: NodePaths, project: str, folder: str) -> float | None:
    """When a job last ran in the folder on this node, or None if nothing says."""
    home = paths.project_home(project)
    for marker in (home / "repo.git" / "logs" / "refs" / "heads" / f"tree-{folder}",
                   home / "repo.git" / "worktrees" / folder / "index"):
        try:
            return marker.stat().st_mtime
        except OSError:
            continue
    return None


def measure(paths: NodePaths) -> tuple[list[Folder], dict[str, Any]]:
    """Every branch folder with its size and last job, and the rest of mulebox's folders:
    `{projects: {name: {home, caches}}, shared: {...}}` in bytes."""
    seen: set[tuple[int, int]] = set()
    folders: list[Folder] = []
    projects: dict[str, dict[str, int]] = {}
    homes = sorted(p for p in paths.projects.iterdir() if p.is_dir()) if paths.projects.is_dir() else []
    for home in homes:
        trees = project_disk.trees(paths, home.name)
        total, each = sizes(home, trees, seen)
        folders += [Folder(home.name, tree.name, each[tree], last_used(paths, home.name, tree.name),
                           slim=DONE if slim.is_slim(paths, home.name, tree.name) else None)
                    for tree in trees]
        projects[home.name] = {"home": total - sum(each.values()), "caches": 0}
    packages = paths.cache / "packages"
    owned = sorted(p for p in packages.iterdir() if p.is_dir()) if packages.is_dir() else []
    tools, browsers = paths.toolchains_dir(), paths.browsers_dir()
    cache_total, cache_each = sizes(paths.cache, [*owned, tools, browsers], seen)
    for folder in owned:
        projects.setdefault(folder.name, {"home": 0, "caches": 0})["caches"] = cache_each[folder]
    shared = {"toolchains": cache_each[tools], "browsers": cache_each[browsers],
              "caches_other": cache_total - sum(cache_each.values())}
    for name, root in (("runners", paths.runners), ("staging", paths.staging), ("jobs", paths.jobs)):
        shared[name] = sizes(root, (), seen)[0] if root.is_dir() else 0
    return folders, {"projects": projects, "shared": shared}


def where(paths: NodePaths) -> dict[str, str]:
    """Where each part is on this node, for the dashboard's "copy path": a project's home is
    `<projects>/<project>`, a branch folder `<projects>/<project>/trees/<folder>`, a project's
    package caches `<packages>/<project>`."""
    return {"projects": str(paths.projects), "packages": str(paths.cache / "packages"),
            "toolchains": str(paths.toolchains_dir()), "browsers": str(paths.browsers_dir()),
            "caches_other": str(paths.cache), "runners": str(paths.runners),
            "staging": str(paths.staging), "jobs": str(paths.jobs)}


def disk(paths: NodePaths) -> dict[str, int]:
    """The disk of the project folders: its size and free space in bytes."""
    usage = shutil.disk_usage(paths.projects if paths.projects.is_dir() else paths.jobs)
    return {"total": usage.total, "free": usage.free}


def parse_size(text: str) -> int | None:
    """A size as Docker prints it (`9.809GB`, `106.5kB`, `0B`), in bytes."""
    found = _DOCKER_SIZE.match(text or "")
    return int(float(found.group(1)) * _UNITS[found.group(2)]) if found else None


def docker(engine: Docker | None) -> dict[str, Any] | None:
    """Docker's totals on this machine, or None without Docker or when it does not answer."""
    if engine is None:
        return None
    try:
        lines = engine.lines("system", "df", "--format", "{{json .}}", timeout_s=DOCKER_TIMEOUT_S)
    except DockerError:
        return None
    out: dict[str, Any] = {}
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        key = {"Images": "images", "Containers": "containers", "Local Volumes": "volumes",
               "Build Cache": "build_cache"}.get(row.get("Type"))
        if key:
            out[key] = {"size": parse_size(row.get("Size", "")),
                        "reclaimable": parse_size(row.get("Reclaimable", "")),
                        "count": int(row["TotalCount"]) if str(row.get("TotalCount", "")).isdigit() else None}
    return out or None
