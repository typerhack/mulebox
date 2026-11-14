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
from mulebox.worker import project_disk, project_work
from mulebox.worker.paths import NodePaths
from mulebox.worker.project_work import DEFAULT_DAYS


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
    project_work.clean(node, paths, used, args.days, args.yes, print,
                       hold=lambda project, work: _held(store, project, work))
    return 0


def _reset(args: argparse.Namespace) -> int:
    node, paths = _load(args)
    store, staging = _local(node)
    project_work.reset(node, paths, args.project, args.branch, args.caches, args.yes, print,
                       after=lambda: staging.remove_base(args.project),
                       hold=lambda project, work: _held(store, project, work))
    return 0
