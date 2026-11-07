"""CLI `mulebox init`: write a project's `.mulebox.yml` from what the project already has.

Reaches no machine. Writes that one file, only if it passes the same check as every other
`.mulebox.yml`, and never replaces one without --force. Exit codes: 0 written, 2 nothing written.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

import yaml

from mulebox.client.commands import UsageError, guarded
from mulebox.client.init_detect import Detected, detect
from mulebox.common.config import PROJECT_FILE, load_project_config


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("init", help=f"write {PROJECT_FILE} for this project from its files")
    parser.add_argument("--check", metavar="COMMAND",
                        help="the project's full gate, instead of working it out")
    parser.add_argument("--print", action="store_true", dest="print_only",
                        help="print the file and write nothing")
    parser.add_argument("--force", action="store_true", help=f"replace an existing {PROJECT_FILE}")
    parser.set_defaults(func=guarded(_init))


def render(found: Detected, gate: str) -> str:
    """The file's text. Empty fields are left out, and notes stay beside what they are about."""
    data: dict[str, object] = {"project": found.project}
    if found.toolchain:
        data["toolchain"] = found.toolchain
    if found.needs:
        data["needs"] = list(dict.fromkeys(found.needs))
    if found.compose:
        data["compose"] = found.compose
    data["env"] = {"CI": "1"}
    if found.install:
        data["install"] = " && ".join(found.install)
    if found.setup:
        data["setup"] = " && ".join(found.setup)
    data["jobs"] = {"check": gate, **{name: command for name, command in found.jobs.items()
                                      if name != "check" and command != gate}}
    header = ["# Written by mulebox init. Commit it once `mulebox check` passes."]
    header += [f"# Check: {note}" for note in found.notes]
    body = yaml.safe_dump(data, sort_keys=False, width=1000)
    return "\n".join(header) + "\n" + body


def _validate(text: str, root: Path) -> None:
    """The real check, on a file beside the project's others, so `compose:` names resolve."""
    handle, name = tempfile.mkstemp(prefix=".mulebox-init-", suffix=".yml", dir=root)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        load_project_config(Path(name))
    finally:
        os.unlink(name)


def _init(args: argparse.Namespace) -> int:
    root = Path.cwd()
    target = root / PROJECT_FILE
    if target.exists() and not (args.force or args.print_only):
        raise UsageError(f"{PROJECT_FILE} already exists; --force replaces it")
    found = detect(root)
    gate = args.check or " && ".join(dict.fromkeys(found.checks))
    if not gate:
        raise UsageError("could not work out how this project is tested; say it with "
                         "`mulebox init --check \"your test command\"`")
    text = render(found, gate)
    _validate(text, root)
    if args.print_only:
        sys.stdout.write(text)
        return 0
    target.write_text(text, encoding="utf-8")
    print(f"wrote {PROJECT_FILE}: `{gate}` is the check")
    for note in found.notes:
        print(f"  check: {note}")
    print("next: mulebox doctor, then mulebox check")
    return 0
