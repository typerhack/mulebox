"""`mulebox project-home`, on a node; the client's `mulebox project` calls it over ssh.

    mulebox project-home list --json
    mulebox project-home clean [--days N] [--yes]
    mulebox project-home reset <project> [--branch NAME] [--caches] [--yes]

Without `--yes`, `clean` and `reset` only say what would go.
"""

import argparse
import json
import sys
import time
from typing import Any

from mulebox.common import units
from mulebox.common.config import NodeConfig, load_node_config
from mulebox.common.errors import MuleboxError
from mulebox.common.ids import new_id
from mulebox.worker import caches, project_disk, project_home, reclaim
from mulebox.worker.docker import Docker
from mulebox.worker.paths import NodePaths

DEFAULT_DAYS = 14


def register(sub: argparse._SubParsersAction) -> None:
    home = sub.add_parser("project-home", help="project folders on this node")
    actions = home.add_subparsers(dest="home_command", metavar="<action>", required=True)
    shown = actions.add_parser("list", help="every project folder and its size")
    shown.add_argument("--json", action="store_true")
    shown.set_defaults(func=_guard(_list))
    clean = actions.add_parser("clean", help="remove branch folders not used for a while")
    clean.add_argument("--days", type=int, default=DEFAULT_DAYS)
    clean.add_argument("--yes", action="store_true", help="really remove them")
    clean.set_defaults(func=_guard(_clean))
    reset = actions.add_parser("reset", help="remove a project's folder, or one branch's")
    reset.add_argument("project")
    reset.add_argument("--branch", help="only this branch")
    reset.add_argument("--caches", action="store_true", help="its package caches too")
    reset.add_argument("--yes", action="store_true", help="really remove it")
    reset.set_defaults(func=_guard(_reset))
    for parser in (shown, clean, reset):
        parser.add_argument("--config", help="node config file")


def _guard(handler: Any) -> Any:
    def run(args: argparse.Namespace) -> int:
        try:
            return handler(args)
        except MuleboxError as exc:
            print(f"mulebox: {exc}", file=sys.stderr)
            return 2
    return run


def _load(args: argparse.Namespace) -> tuple[NodeConfig, NodePaths]:
    node = load_node_config(args.config)
    return node, NodePaths.from_config(node.roots)


def _local(node: NodeConfig) -> tuple[Any, Any]:
    from mulebox.coordinator.errors import BadRequest
    from mulebox.coordinator.node import open_local

    if node.coordinator is not None:
        raise BadRequest("run this on the coordinator's machine")
    return open_local(node)


def _reclaimer(node: NodeConfig, paths: NodePaths) -> project_disk.Reclaim:
    return lambda tree: reclaim.reclaim_tree(Docker(), paths, tree, new_id("job"), node.name)


def _size(path: Any) -> str:
    return units.size(caches.size_of(path))


def _held(store: Any, project: str, work: Any) -> None:
    from mulebox.coordinator import holds

    holds.take(store, project, time.time())
    try:
        work()
    finally:
        holds.release(store, project)


def _list(args: argparse.Namespace) -> int:
    _, paths = _load(args)
    rows = project_disk.listing(paths)
    if args.json:
        print(json.dumps(rows))
    else:
        for row in rows:
            print(f"{row['project']}\t{units.size(row['size'])}\t{row['folder']}")
    return 0


def _clean(args: argparse.Namespace) -> int:
    from mulebox.coordinator import projects

    node, paths = _load(args)
    store, _ = _local(node)
    with store.read() as conn:
        used = projects.branches(conn)
    cutoff = time.time() - args.days * 86400
    count = 0
    for row in project_disk.listing(paths):
        project = row["project"]
        names = [tree["folder"] for tree in row["trees"]]
        for name in project_disk.unused(names, used.get(project, {}), cutoff):
            count += 1
            print(f"{project}: {name}, {_size(paths.project_home(project) / 'trees' / name)}")
            if args.yes:
                _held(store, project, lambda p=project, n=name: project_disk.remove_worktree(
                    paths, p, n, _reclaimer(node, paths)))
    print(f"{'removed' if args.yes else 'would remove'} {count} branch folders; each is set up "
          "again by its next job")
    return 0


def _reset(args: argparse.Namespace) -> int:
    node, paths = _load(args)
    store, staging = _local(node)
    home = paths.project_home(args.project)
    target = home / "trees" / project_home.slug(args.branch) if args.branch else home
    print(f"{target}, {_size(target)}" if target.is_dir() else f"no folder at {target}")
    if args.caches:
        print(f"{paths.packages_dir(args.project)}, {_size(paths.packages_dir(args.project))}")
    if not args.yes:
        print("nothing removed: add --yes; the next job sets it up again")
        return 0

    def work() -> None:
        reclaimer = _reclaimer(node, paths)
        if args.branch and target.is_dir():
            project_disk.remove_worktree(paths, args.project, target.name, reclaimer)
        elif not args.branch:
            project_disk.remove_project(paths, args.project, reclaimer)
            staging.remove_base(args.project)
        if args.caches:
            caches.clear(paths, args.project, Docker())

    _held(store, args.project, work)
    print("removed; the next job sets it up again")
    return 0
