"""Package caches: downloads kept between jobs of one project, under the cache root.

`needs: [cache-pnpm]` gives a job `<cache>/packages/<project>/pnpm`, in the spirit of the
shared Playwright folder; `cache-npm`, `cache-composer`, `cache-pip`, and on a Mac node
`cache-spm` (Swift packages) and `cache-cocoapods` work the same way. It is opt-in and per project on purpose. A cache is written by
jobs and read by later jobs, so a job can leave something in it for the next one. That
stays inside one project: another project has its own folder and cannot be reached through
this one, and a job's log says which cache it used. Within a project, every branch shares
it. pnpm checks packages against the lockfile's hashes; Composer only where the lockfile
has one. This is not a defence against a hostile project (docs/design.md, Safety).

Commands on the machine get the tool's own setting. Containers get what the project mounts:
`MULEBOX_CACHE_<TOOL>` holds the folder, and that folder is the one writable bind outside
the checkout that compose_policy.py lets through. An external volume stays refused.

`<cache>/packages/` holds downloads only. A later install step run by mulebox can add its
results beside it, keyed on lockfile, toolchain and image, without moving anything here.

A container often runs as root, so what it leaves is root's. After a compose job the worker
gives the project's caches back with the same helper it uses for job folders (cleaner.py).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mulebox.common import package_cache
from mulebox.common.ids import new_id
from mulebox.common.safepath import RemovalDenied, confirm_dir, ensure_dir, remove_tree
from mulebox.worker import reclaim
from mulebox.worker.docker import Docker
from mulebox.worker.paths import NodePaths


@dataclass(frozen=True)
class Tool:
    capability: str
    folder: str
    mount_variable: str  # the folder, for a project's compose file
    settings: tuple[str, ...]  # what makes the tool use the folder on the machine
    hint: str = ""  # for a tool no setting reaches: what the project passes it


TOOLS = (
    # pnpm 11 reads only its own prefix; older versions read only npm's.
    Tool(package_cache.PNPM, "pnpm", "MULEBOX_CACHE_PNPM",
         ("pnpm_config_store_dir", "npm_config_store_dir")),
    Tool(package_cache.COMPOSER, "composer", "MULEBOX_CACHE_COMPOSER", ("COMPOSER_CACHE_DIR",)),
    Tool(package_cache.NPM, "npm", "MULEBOX_CACHE_NPM", ("npm_config_cache",)),
    Tool(package_cache.PIP, "pip", "MULEBOX_CACHE_PIP", ("PIP_CACHE_DIR",)),
    # SwiftPM reads no setting for its cache: the project passes the folder on the command line.
    Tool(package_cache.SPM, "spm", "MULEBOX_CACHE_SPM", (),
         "pass it as `xcodebuild -packageCachePath \"$MULEBOX_CACHE_SPM\"` or `swift build "
         "--cache-path \"$MULEBOX_CACHE_SPM\"`"),
    Tool(package_cache.COCOAPODS, "cocoapods", "MULEBOX_CACHE_COCOAPODS", ("CP_CACHE_DIR",)),
)


@dataclass(frozen=True)
class JobCaches:
    env: dict[str, str]
    folders: tuple[Path, ...]  # compose_policy.py lets these be mounted writable
    notes: tuple[str, ...]


def for_job(paths: NodePaths, project: str, needs: Sequence[str]) -> JobCaches:
    """The caches a job asked for, created through safepath and proven to be real folders.
    A folder a job turned into a symlink stops here, with an error, instead of being used."""
    env: dict[str, str] = {}
    folders: list[Path] = []
    notes: list[str] = []
    for tool in TOOLS:
        if tool.capability not in needs:
            continue
        folder = ensure_dir(paths.package_cache(project, tool.folder), paths.roots)
        confirm_dir(folder, paths.roots)
        folders.append(folder)
        env |= {tool.mount_variable: str(folder), **dict.fromkeys(tool.settings, str(folder))}
        hint = f"; {tool.hint}" if tool.hint else ""
        notes.append(f"package cache {tool.folder}: shared by every job of {project} on this "
                     f"machine (${tool.mount_variable}){hint}")
        if not any(folder.iterdir()):
            notes.append(f"package cache {tool.folder} is empty, so this job downloads "
                         "everything; later jobs reuse it")
    return JobCaches(env, tuple(folders), tuple(notes))


def give_back(docker: Docker, paths: NodePaths, project: str, job_id: str, worker: str) -> None:
    """Make the worker's user own the project's caches again, if it has any."""
    if paths.packages_dir(project).is_dir():
        reclaim.reclaim_cache(docker, paths, project, job_id, worker)


def size_of(folder: Path) -> int:
    total = 0
    for base, _, files in os.walk(folder):  # does not follow symlinks
        for name in files:
            try:
                total += os.lstat(os.path.join(base, name)).st_size
            except OSError:
                continue
    return total


def listing(paths: NodePaths) -> list[tuple[str, str, int]]:
    """(project, tool, bytes) of every cache on this machine."""
    base = paths.cache / "packages"
    known = {tool.folder for tool in TOOLS}
    found = []
    for project in sorted(base.iterdir()) if base.is_dir() else ():
        if project.is_symlink() or not project.is_dir():
            continue
        for entry in sorted(project.iterdir()):
            if entry.name in known and entry.is_dir() and not entry.is_symlink():
                found.append((project.name, entry.name, size_of(entry)))
    return found


def clear(paths: NodePaths, project: str, docker: Docker | None = None) -> None:
    """Remove a project's caches; the next job fetches everything again. The way out when a
    cache is suspect. Run it while no job of the project runs."""
    folder = paths.packages_dir(project)
    try:
        remove_tree(folder, paths.roots)
    except RemovalDenied:
        if docker is None:
            raise
        reclaim.reclaim_cache(docker, paths, project, new_id("job"), "cache-clear")
        remove_tree(folder, paths.roots)
