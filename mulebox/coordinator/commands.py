"""CLI subcommands of the coordinator package (docs/interfaces-m1.md, CLI).

`rpc`, `rpc-upload`, `rpc-download` and `coordinator serve`. They load the node config
(`--node-config` overrides the default path) and open the store under the staging root.
"""

import argparse
import sys
from pathlib import Path

from mulebox.common.config import load_node_config
from mulebox.common.errors import MuleboxError
from mulebox.common.log import setup_logging
from mulebox.coordinator import daemon, rpc
from mulebox.coordinator.node import open_local

EXIT_CONFIG = 2


def register(sub: argparse._SubParsersAction) -> None:
    """Add this package's subcommands. Each sets func=handler(args) -> int."""
    p = sub.add_parser("rpc", help="answer one protocol request from stdin (used over ssh)")
    _node_option(p)
    p.set_defaults(func=_rpc)

    p = sub.add_parser("rpc-upload", help="receive a job snapshot (tar.gz) on stdin")
    p.add_argument("job_id")
    p.add_argument("sha256")
    _node_option(p)
    p.set_defaults(func=_upload)

    p = sub.add_parser("rpc-download", help="write a job snapshot (tar.gz) to stdout")
    p.add_argument("job_id")
    _node_option(p)
    p.set_defaults(func=_download)

    p = sub.add_parser("coordinator", help="coordinator service")
    coord = p.add_subparsers(dest="coordinator_command", metavar="<command>", required=True)
    serve = coord.add_parser("serve", help="run lease sweeps (recovery first)")
    _node_option(serve)
    serve.add_argument("--log-level", default="INFO")
    serve.set_defaults(func=_serve)


def _node_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--node-config", type=Path, default=None, help=argparse.SUPPRESS)


def _with_store(args: argparse.Namespace, action) -> int:
    setup_logging("WARNING")  # stdout carries the protocol; logs go to stderr
    try:
        node = load_node_config(args.node_config)
        # M1 has one node: the cluster-wide slot limit is that node's slot count.
        args.cluster_slots = node.slots
        store, staging = open_local(node)
    except MuleboxError as exc:
        print(f"mulebox: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        return action(store, staging)
    finally:
        store.close()


def _rpc(args: argparse.Namespace) -> int:
    return _with_store(args, lambda store, staging: rpc.run_rpc(
        store, staging, sys.stdin.buffer, sys.stdout.buffer, sys.stderr,
        cluster_slots=args.cluster_slots))


def _upload(args: argparse.Namespace) -> int:
    return _with_store(args, lambda store, staging: rpc.run_upload(
        store, staging, args.job_id, args.sha256, sys.stdin.buffer, sys.stdout.buffer,
        sys.stderr))


def _download(args: argparse.Namespace) -> int:
    return _with_store(args, lambda store, staging: rpc.run_download(
        store, staging, args.job_id, sys.stdout.buffer, sys.stderr))


def _serve(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)
    try:
        node = load_node_config(args.node_config)
        return daemon.serve(node)
    except MuleboxError as exc:
        print(f"mulebox: {exc}", file=sys.stderr)
        return EXIT_CONFIG
