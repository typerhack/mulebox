"""CLI subcommands for runner hooks (docs/interfaces-m3.md, Hook entry points).

    mulebox runner-hook started     # ACTIONS_RUNNER_HOOK_JOB_STARTED
    mulebox runner-hook completed   # ACTIONS_RUNNER_HOOK_JOB_COMPLETED
"""

import argparse
import os
import sys

from mulebox.common.errors import MuleboxError


def register(sub: argparse._SubParsersAction) -> None:
    """Add the subcommands. Each sets func=handler(args) -> int."""
    hook = sub.add_parser("runner-hook",
                          help="GitHub Actions runner job hook: hold a build slot")
    hook.add_argument("event", choices=("started", "completed"),
                      help="started: reserve and wait for a slot; completed: release it")
    hook.add_argument("--config", help="node config file (default ~/.config/mulebox/node.toml)")
    hook.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    from mulebox.common.config import load_node_config
    from mulebox.common.log import setup_logging
    from mulebox.runners import hooks
    from mulebox.worker.commands import open_link
    from mulebox.worker.paths import NodePaths

    if args.event == "started":
        from mulebox.runners import guard

        if not guard.admit(os.environ, sys.stdout):  # first, before anything that can fail
            return 1
    setup_logging()
    failed = 1 if args.event == "started" else 0  # a completed hook never fails the job
    try:
        node = load_node_config(args.config)
        paths = NodePaths.from_config(node.roots)
        link = open_link(node, paths)
    except (MuleboxError, ImportError, OSError) as exc:
        print(f"mulebox: runner hook cannot start: {exc}", file=sys.stderr)
        return failed
    if args.event == "started":
        return hooks.started(os.environ, node.name, link, paths)
    return hooks.completed(os.environ, link, paths)
