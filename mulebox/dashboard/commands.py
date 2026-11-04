"""CLI `mulebox dashboard serve` (build machine) and `mulebox dashboard open` (laptop).

`serve` reads node.toml's `[dashboard]`: `off` exits 0 with a note (so an enabled unit
does not restart in a loop), `local` serves on 127.0.0.1 only, `lan` is refused until
it exists (docs/interfaces-m2.md). There is deliberately no option to bind another
address. The store is opened read-only.

`open` reads the client config and tunnels to the coordinator machine (client/tunnel.py).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from mulebox.client import tunnel
from mulebox.client.commands import guarded
from mulebox.common.config import DEFAULT_DASHBOARD_PORT, load_client_config, load_node_config
from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger, setup_logging

BIND_HOST = "127.0.0.1"
EXIT_CONFIG = 2
_log = get_logger(__name__)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("dashboard", help="web dashboard (serve on the build machine, open "
                       "from the laptop)")
    dash = p.add_subparsers(dest="dashboard_command", metavar="<command>", required=True)

    serve = dash.add_parser("serve", help="serve the dashboard on 127.0.0.1 (build machine)")
    serve.add_argument("--port", type=int, default=None, help="override node.toml's port")
    serve.add_argument("--node-config", type=Path, default=None, help=argparse.SUPPRESS)
    serve.add_argument("--log-level", default="INFO")
    serve.set_defaults(func=_serve)

    opener = dash.add_parser("open", help="open an SSH tunnel and the dashboard in a browser")
    opener.add_argument("--port", type=int, default=DEFAULT_DASHBOARD_PORT,
                        help=f"local port of the tunnel (default {DEFAULT_DASHBOARD_PORT})")
    opener.add_argument("--remote-port", type=int, default=DEFAULT_DASHBOARD_PORT,
                        help="dashboard port on the build machine (node.toml, default "
                        f"{DEFAULT_DASHBOARD_PORT})")
    opener.add_argument("--no-browser", action="store_true", help="only print the URL")
    opener.set_defaults(func=guarded(_open))


def _open(args: argparse.Namespace) -> int:
    return tunnel.open_dashboard(load_client_config(), args.port, args.remote_port,
                                 sys.stderr, browser=not args.no_browser)


def _serve(args: argparse.Namespace) -> int:
    setup_logging(args.log_level)
    try:
        node = load_node_config(args.node_config)
    except MuleboxError as exc:
        print(f"mulebox: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    mode = node.dashboard.get("mode", "local")
    if mode == "off":
        print("mulebox: the dashboard is off in node.toml ([dashboard] mode)", file=sys.stderr)
        return 0
    if mode != "local":
        print(f"mulebox: dashboard mode {mode!r} is not available yet; use mode = \"local\" "
              "and `mulebox dashboard open` from the laptop", file=sys.stderr)
        return EXIT_CONFIG
    port = args.port if args.port is not None else node.dashboard.get("port",
                                                                    DEFAULT_DASHBOARD_PORT)
    return run(node, port)


def run(node, port: int) -> int:
    """Serve until stopped (SIGTERM/SIGINT). Imports aiohttp only here."""
    from aiohttp import web

    from mulebox.coordinator.node import open_local
    from mulebox.dashboard.data import DashboardData
    from mulebox.dashboard.events import EventBus
    from mulebox.dashboard.hub import Hub
    from mulebox.dashboard.server import build_app

    try:
        store, staging = open_local(node, readonly=True)
    except (MuleboxError, sqlite3.Error) as exc:
        print(f"mulebox: cannot open the coordinator's store read-only: {exc} "
              "(is the coordinator installed and started?)", file=sys.stderr)
        return EXIT_CONFIG
    try:
        data = DashboardData(store, staging)
        app = build_app(data, Hub(data, EventBus(), node.roots))
        _log.info("dashboard on http://%s:%d (local mode)", BIND_HOST, port)
        web.run_app(app, host=BIND_HOST, port=port, print=None, access_log=None,
                    shutdown_timeout=5)
    finally:
        store.close()
    return 0
