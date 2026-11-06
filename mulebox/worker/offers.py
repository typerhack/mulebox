"""What this machine can offer jobs, found out rather than typed into node.toml.

`mulebox node-offers` on a build machine; `mulebox setup` runs it. It fills `capabilities` only
while the list is empty, so a list a person wrote is never changed. `playwright` is not found out
here: it needs system packages that only root installs.
"""

import argparse
import json
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from mulebox.common.config import ConfigError, load_node_config, node_config_path
from mulebox.common.errors import MuleboxError

Check = Callable[[Sequence[str]], bool]
_TIMEOUT_S = 30
_LINE = re.compile(r"^capabilities[ \t]*=[ \t]*\[[ \t]*\][ \t]*$", re.MULTILINE)


def _succeeds(argv: Sequence[str]) -> bool:
    try:
        return subprocess.run(argv, capture_output=True, timeout=_TIMEOUT_S,
                              stdin=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def docker_state(check: Check = _succeeds) -> str:
    """`ok`, `no-access` (Docker is there, this user cannot use it) or `missing`."""
    if not check(["docker", "--version"]) or not check(["docker", "compose", "version"]):
        return "missing"
    return "ok" if check(["docker", "info"]) else "no-access"


def fill_capabilities(path: Path, found: list[str]) -> list[str]:
    """Put `found` in an empty `capabilities = []`; return what was added."""
    text = path.read_text(encoding="utf-8")
    if not found or not _LINE.search(text):
        return []
    path.write_text(_LINE.sub(f"capabilities = {json.dumps(found)}", text), encoding="utf-8")
    return found


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("node-offers", help="find out what this build machine offers jobs")
    parser.add_argument("--config", help="node config file")
    parser.add_argument("--write", action="store_true", help="fill an empty capabilities list")
    parser.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    docker = docker_state()
    path = Path(args.config) if args.config else node_config_path()
    try:
        added = (fill_capabilities(path, ["docker"] if docker == "ok" else [])
                 if args.write else [])
        node = load_node_config(path)
    except (ConfigError, OSError, MuleboxError) as exc:
        print(f"mulebox: {exc}")
        return 2
    print(json.dumps({"docker": docker, "added": added, "capabilities": list(node.capabilities)}))
    return 0
