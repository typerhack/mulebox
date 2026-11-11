"""CLI `mulebox dashboard password|cert|firewall`, and the checks before `lan` mode serves.

No aiohttp at import time: the dev machine imports this through the CLI.
"""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import ssl
import sys
import time
from pathlib import Path

from mulebox.common.config import load_node_config
from mulebox.common.errors import MuleboxError
from mulebox.dashboard import cert, firewall, password
from mulebox.dashboard.lanfiles import LanNotReady, lan_dir
from mulebox.dashboard.session import LanAccess, LoginLimiter, Sessions

EXIT_CONFIG = 2


def register(dash: argparse._SubParsersAction) -> None:
    pw = dash.add_parser("password", help="set the LAN sign-in password (node)")
    pw.set_defaults(func=_guarded(_password))
    made = dash.add_parser("cert", help="create the certificate for lan_tls (node)")
    made.add_argument("--force", action="store_true", help="replace an existing certificate")
    made.set_defaults(func=_guarded(_cert))
    wall = dash.add_parser("firewall", help="print the root script for the LAN firewall rule")
    wall.set_defaults(func=_guarded(_firewall))
    for parser in (pw, made, wall):
        parser.add_argument("--node-config", type=Path, default=None, help=argparse.SUPPRESS)


def _guarded(func):
    def run(args: argparse.Namespace) -> int:
        try:
            return func(args)
        except MuleboxError as exc:
            print(f"mulebox: {exc}", file=sys.stderr)
            return EXIT_CONFIG
    return run


def _lan_settings(args: argparse.Namespace) -> dict:
    dashboard = load_node_config(args.node_config).dashboard
    if not dashboard.get("lan_address"):
        raise LanNotReady("set lan_range and lan_address under [dashboard] in node.toml first")
    return dashboard


def _read_new_password() -> str:
    if not sys.stdin.isatty():  # for scripts; never an argument, which `ps` would show
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("New dashboard password: ")
    if first != getpass.getpass("Again: "):
        raise LanNotReady("the two passwords differ; nothing changed")
    return first


def _password(args: argparse.Namespace) -> int:
    new = _read_new_password()
    problem = password.check_new(new)
    if problem:
        raise LanNotReady(problem)
    password.save(lan_dir(args.node_config), new)
    print("Password saved. Restart the service to apply it and sign everyone out:\n"
          "  systemctl --user restart mulebox-dashboard")
    return 0


def _cert(args: argparse.Namespace) -> int:
    address = _lan_settings(args)["lan_address"]
    directory = lan_dir(args.node_config)
    existing = directory / cert.CERT_NAME
    if existing.exists() and not args.force:
        raise LanNotReady(f"{existing} already exists. Replacing it means trusting the new "
                          "one on every device again; use --force to do that")
    made = cert.generate(directory, address)
    print(f"Certificate for {address}: {made}\nSHA-256 {cert.fingerprint(made)}\n"
          "Copy that file to each device, trust it there, and compare the fingerprint.\n"
          f"Valid for {cert.VALID_DAYS} days.")
    return 0


def _firewall(args: argparse.Namespace) -> int:
    settings = _lan_settings(args)
    print(firewall.script(settings["lan_range"], settings["lan_port"]), end="")
    return 0


def prepare(dashboard: dict, config_path: Path | None
            ) -> tuple[LanAccess, ssl.SSLContext | None]:
    """All `lan` mode needs before it serves. Raises LanNotReady naming the missing step."""
    directory = lan_dir(config_path)
    stored = password.load(directory) if dashboard.get("lan_password", True) else None
    address, tls = dashboard["lan_address"], dashboard.get("lan_tls", False)
    if tls:
        cert.check(directory, address)
    access = LanAccess(network=ipaddress.ip_network(dashboard["lan_range"]),
                       hosts=frozenset({address}), listen=(address, dashboard["lan_port"]),
                       password_hash=stored, sessions=Sessions(time.time),
                       limiter=LoginLimiter(time.time))
    return access, cert.server_context(directory) if tls else None
