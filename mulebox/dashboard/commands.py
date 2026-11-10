"""CLI `mulebox dashboard serve` (build machine) and `mulebox dashboard open` (laptop).

`serve` reads node.toml's `[dashboard]`: `off` exits 0 with a note (so an enabled unit
does not restart in a loop), `local` serves on 127.0.0.1 only, and `lan` also serves
on `lan_address` once its setup is complete (docs/interfaces-m2.md). There is
deliberately no option to bind any other address. The store is opened read-only; the
optional cancel button goes through `mulebox rpc` (canceller.py).

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
from mulebox.dashboard import lan_commands

BIND_HOST = "127.0.0.1"
EXIT_CONFIG = 2
_log = get_logger(__name__)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("dashboard", help="web dashboard (serve on the build machine, open "
                       "from the laptop)")
    dash = p.add_subparsers(dest="dashboard_command", metavar="<command>", required=True)

    serve = dash.add_parser("serve", help="serve the dashboard (build machine)")
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
    lan_commands.register(dash)


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
    lan = None
    if mode == "lan":
        try:
            lan = lan_commands.prepare(node.dashboard, args.node_config)
        except MuleboxError as exc:
            print(f"mulebox: {exc}", file=sys.stderr)
            return EXIT_CONFIG
    port = args.port if args.port is not None else node.dashboard.get("port",
                                                                    DEFAULT_DASHBOARD_PORT)
    return run(node, port, lan, args.node_config)


def _canceller(node, access, config_path: Path | None):
    """The link the dashboard's controls write through; none with `controls = false`."""
    from mulebox.dashboard.canceller import Canceller

    if not node.dashboard.get("controls", True):
        _log.info("the dashboard's controls are off (controls = false)")
        return None
    return Canceller(config_path)


def run(node, port: int, lan=None, config_path: Path | None = None) -> int:
    """Serve until stopped (SIGTERM/SIGINT). Imports aiohttp only here."""
    from mulebox.coordinator.node import open_local
    from mulebox.dashboard.data import DashboardData
    from mulebox.dashboard.events import EventBus
    from mulebox.dashboard.hub import Hub
    from mulebox.dashboard.listeners import Listener, serve
    from mulebox.dashboard.server import build_app

    try:
        store, staging = open_local(node, readonly=True)
    except (MuleboxError, sqlite3.Error) as exc:
        print(f"mulebox: cannot open the coordinator's store read-only: {exc} "
              "(is the coordinator installed and started?)", file=sys.stderr)
        return EXIT_CONFIG
    try:
        data = DashboardData(store, staging)
        access, tls = lan if lan else (None, None)
        hub = Hub(data, EventBus(), node.roots, local_name=node.name)
        app = build_app(data, hub, lan=access, canceller=_canceller(node, access, config_path))
        listeners = [Listener(BIND_HOST, port)]
        _log.info("dashboard on http://%s:%d", BIND_HOST, port)
        if access is not None:
            address, lan_port = access.listen
            listeners.append(Listener(address, lan_port, tls))
            _log.info("dashboard on %s://%s:%d", "https" if tls else "http", address, lan_port)
            if access.password_hash is None:
                _log.warning("no password on the LAN address: lan_password = false")
        serve(app, listeners)
    except OSError as exc:  # Wi-Fi not up yet, port busy: the unit retries
        _log.error("cannot listen: %s", exc)
        return 1
    finally:
        store.close()
    return 0
