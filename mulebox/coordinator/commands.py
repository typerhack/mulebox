"""CLI subcommands of the coordinator package (docs/interfaces-m1.md, CLI).

`rpc`, `rpc-upload`, `rpc-download` and `coordinator serve`. They load the node config
(`--node-config` overrides the default path) and open the store under the staging root.
`ssh-gate` and `authorize-worker` are for workers on other machines (worker_keys.py).
"""

import argparse
import os
import sys
from pathlib import Path

from mulebox.common import dashboard_address
from mulebox.common.config import load_node_config
from mulebox.common.errors import MuleboxError
from mulebox.common.log import setup_logging
from mulebox.coordinator import daemon, rpc, worker_keys
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

    p = sub.add_parser("rpc-upload-plan", help="say which files of a snapshot to send")
    p.add_argument("job_id")
    _node_option(p)
    p.set_defaults(func=_upload_plan)

    p = sub.add_parser("rpc-upload-delta", help="receive the changed files of a snapshot")
    p.add_argument("job_id")
    p.add_argument("sha256")
    p.add_argument("digest")
    _node_option(p)
    p.set_defaults(func=_upload_delta)

    p = sub.add_parser("rpc-download", help="write a job snapshot (tar.gz) to stdout")
    p.add_argument("job_id")
    _node_option(p)
    p.set_defaults(func=_download)

    p = sub.add_parser("ssh-gate", help=argparse.SUPPRESS)  # forced by a worker key
    _node_option(p)
    p.set_defaults(func=_gate)

    p = sub.add_parser("authorize-worker",
                       help="let a worker's key (on stdin) reach this coordinator, for rpc only")
    p.add_argument("name", help="the worker's name")
    p.set_defaults(func=_authorize)

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
        # the least the cluster holds; more workers add their slots (workers.cluster_limit)
        args.cluster_slots = node.slots
        args.dashboard = dashboard_address.where(node.dashboard)
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
        cluster_slots=args.cluster_slots, dashboard=args.dashboard))


def _upload(args: argparse.Namespace) -> int:
    return _with_store(args, lambda store, staging: rpc.run_upload(
        store, staging, args.job_id, args.sha256, sys.stdin.buffer, sys.stdout.buffer,
        sys.stderr))


def _upload_plan(args: argparse.Namespace) -> int:
    return _with_store(args, lambda store, staging: rpc.run_upload_plan(
        store, staging, args.job_id, sys.stdin.buffer, sys.stdout.buffer, sys.stderr))


def _upload_delta(args: argparse.Namespace) -> int:
    return _with_store(args, lambda store, staging: rpc.run_upload_delta(
        store, staging, args.job_id, args.sha256, args.digest, sys.stdin.buffer,
        sys.stdout.buffer, sys.stderr))


def _download(args: argparse.Namespace) -> int:
    return _with_store(args, lambda store, staging: rpc.run_download(
        store, staging, args.job_id, sys.stdout.buffer, sys.stderr))


def _gate(args: argparse.Namespace) -> int:
    try:
        command, job_id = worker_keys.gate_command(os.environ.get("SSH_ORIGINAL_COMMAND"))
    except worker_keys.GateRefused as exc:
        print(f"mulebox: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if command == "rpc-download":
        args.job_id = job_id
        return _download(args)
    return _with_store(args, lambda store, staging: rpc.run_rpc(
        store, staging, sys.stdin.buffer, sys.stdout.buffer, sys.stderr,
        cluster_slots=args.cluster_slots, dashboard=args.dashboard,
        allowed=worker_keys.WORKER_MESSAGES))


def _authorize(args: argparse.Namespace) -> int:
    try:
        path = worker_keys.authorize(args.name, sys.stdin.read(), Path.home())
    except (worker_keys.GateRefused, OSError) as exc:
        print(f"mulebox: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    print(f"mulebox: {args.name} may now reach this coordinator, for rpc only ({path})",
          file=sys.stderr)
    return 0


def _serve(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)
    try:
        node = load_node_config(args.node_config)
        return daemon.serve(node)
    except MuleboxError as exc:
        print(f"mulebox: {exc}", file=sys.stderr)
        return EXIT_CONFIG
