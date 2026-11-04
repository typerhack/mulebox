"""CLI subcommands of the worker package (docs/interfaces-m1.md, CLI).

    mulebox worker serve
    mulebox toolchain install <name> <version>
    mulebox toolchain list
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from typing import Any

from mulebox.common.config import DEFAULT_REMOTE_BIN, NodeConfig, load_node_config
from mulebox.common.errors import MuleboxError
from mulebox.common.log import setup_logging
from mulebox.worker.docker import Docker
from mulebox.worker.paths import NodePaths


def register(sub: argparse._SubParsersAction) -> None:
    """Add this package's subcommands. Each sets func=handler(args) -> int."""
    worker = sub.add_parser("worker", help="run the worker on a build machine")
    worker_sub = worker.add_subparsers(dest="worker_command", metavar="<action>", required=True)
    serve = worker_sub.add_parser("serve", help="claim and run jobs (recovery first)")
    serve.add_argument("--config", help="node config file (default ~/.config/mulebox/node.toml)")
    serve.set_defaults(func=_serve)

    tool = sub.add_parser("toolchain", help="install or list pinned toolchains")
    tool_sub = tool.add_subparsers(dest="toolchain_command", metavar="<action>", required=True)
    install = tool_sub.add_parser("install", help="install a toolchain (node, pnpm)")
    install.add_argument("name", help="node or pnpm")
    install.add_argument("version", help="exact version, e.g. 22.22.3")
    install.add_argument("--config", help="node config file")
    install.set_defaults(func=_install)
    listing = tool_sub.add_parser("list", help="list installed toolchains")
    listing.add_argument("--config", help="node config file")
    listing.set_defaults(func=_list)


def _load(args: argparse.Namespace) -> tuple[NodeConfig, NodePaths]:
    node = load_node_config(getattr(args, "config", None))
    return node, NodePaths.from_config(node.roots)


def _fail(exc: Exception) -> int:
    print(f"mulebox: {exc}", file=sys.stderr)
    return 2


def _install(args: argparse.Namespace) -> int:
    from mulebox.worker import toolchains

    try:
        _, paths = _load(args)
        path = toolchains.install(paths, args.name, args.version)
    except MuleboxError as exc:
        return _fail(exc)
    print(f"{args.name} {args.version}: {path}")
    return 0


def _list(args: argparse.Namespace) -> int:
    from mulebox.worker import toolchains

    try:
        _, paths = _load(args)
    except MuleboxError as exc:
        return _fail(exc)
    for name, version in toolchains.installed(paths):
        print(f"{name}\t{version}")
    return 0


def open_link(node: NodeConfig, paths: NodePaths) -> Any:
    """SSH link to a remote coordinator, or the local link to the store on this machine.

    The local store and staging come from `coordinator.node.open_local`.
    """
    from mulebox.worker.link import LocalLink, SSHLink

    if node.coordinator is not None:
        return SSHLink(node.coordinator, DEFAULT_REMOTE_BIN)
    from mulebox.coordinator.node import open_local

    store, staging = open_local(node)
    return LocalLink(store, staging, cluster_slots=node.slots)


def _executor() -> Any:
    if sys.platform.startswith("linux"):
        from mulebox.worker.systemd import SystemdExecutor

        return SystemdExecutor()
    from mulebox.worker.executor import SubprocessExecutor

    return SubprocessExecutor()


def _serve(args: argparse.Namespace) -> int:
    from mulebox.worker.agent import serve

    setup_logging()
    try:
        node, paths = _load(args)
        if "worker" not in node.roles:
            raise MuleboxError(f"node {node.name} does not have the 'worker' role")
        link = open_link(node, paths)
    except (MuleboxError, ImportError) as exc:
        return _fail(exc)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    serve(node, link, _executor(), paths=paths, stop=stop, docker=Docker())
    return 0
