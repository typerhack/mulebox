"""CLI `mulebox skill install|update|status`, run by a person, never by an agent on its own.

Without `--config-dir` they cover every Claude config folder that exists here
(client/skill_install.py). `status` changes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from mulebox.client import skill_install
from mulebox.client.commands import UsageError, guarded
from mulebox.client.contract import SCHEMA
from mulebox.client.skill_install import Copy

Action = Callable[[Copy, str], str]


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("skill", help="install, update or check the agent skill")
    actions = parser.add_subparsers(dest="skill_command", metavar="<action>", required=True)
    for name, handler, text in (
        ("install", _install, "add the skill to the Claude config folders that lack it"),
        ("update", _update, "replace out-of-date copies with this mulebox's skill"),
        ("status", _status, "show each copy against this mulebox's skill; changes nothing"),
    ):
        action = actions.add_parser(name, help=text)
        action.add_argument("--config-dir", action="append", type=Path, default=[],
                            help="this folder instead of those found; may repeat")
        if name == "status":
            action.add_argument("--json", action="store_true", help="stable keys for tools")
        action.set_defaults(func=guarded(handler))


def found_folders() -> list[Path]:
    return skill_install.config_folders(os.environ, Path.home())


def _folders(args: argparse.Namespace) -> list[Path]:
    for folder in args.config_dir:
        if not folder.is_dir():
            raise UsageError(f"no such folder: {folder}")
    folders = args.config_dir or found_folders()
    if not folders:
        raise UsageError("no Claude config folder found (~/.claude, ~/.claude-work or "
                         f"{skill_install.ENV_FOLDER}); name one with --config-dir")
    return folders


def _apply(args: argparse.Namespace, action: Action) -> int:
    packaged = skill_install.packaged_text()
    try:
        for copy in skill_install.inspect_all(_folders(args), packaged):
            print(f"{copy.folder}: {action(copy, packaged)}")
    except OSError as exc:
        raise UsageError(f"cannot write the skill: {exc}") from exc
    return 0


def _install(args: argparse.Namespace) -> int:
    return _apply(args, skill_install.install)


def _update(args: argparse.Namespace) -> int:
    return _apply(args, skill_install.update)


def _status(args: argparse.Namespace) -> int:
    packaged = skill_install.packaged_text()
    folders = args.config_dir or found_folders()
    copies = skill_install.inspect_all(folders, packaged)
    if args.json:
        rows = [{"folder": str(c.folder), "state": c.state, "schema": c.schema} for c in copies]
        sys.stdout.write(json.dumps({"contract_schema": SCHEMA, "copies": rows}, indent=2) + "\n")
        return 0
    print(f"this mulebox: contract schema {SCHEMA}")
    for copy in copies:
        print(f"{copy.folder}: {copy.state}")
    if not copies:
        print("no Claude config folder found")
    return 0
