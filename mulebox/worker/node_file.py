"""A setting changed from afar, written into the node's own node.toml (design.md, Node settings).

Only `slots` and `priority` (common/node_settings.py), as top-level lines: an existing
`slots = ...` line is replaced whole, a missing one goes in before the first table, and every
other line, comments too, stays as it was. The new text must read as a node config with the same
reader the service uses before it is written. It is read and written through safefile, with the
folder above node.toml's own as the root: a symlink at node.toml or its folder is refused, and
the file is replaced in one rename, so a reader never sees half of it.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from mulebox.common import node_settings, safefile
from mulebox.common.config import ConfigError, NodeConfig, node_config_from
from mulebox.common.errors import MuleboxError
from mulebox.common.roots import Roots

_TABLE = re.compile(r"^\s*\[", re.MULTILINE)


class NodeFileError(MuleboxError):
    """node.toml could not take the change; the message says why."""


def _line(key: str) -> re.Pattern[str]:
    return re.compile(rf"^[ \t]*{key}[ \t]*=.*$", re.MULTILINE)


def with_settings(text: str, changes: dict[str, Any]) -> str:
    """`text` with each of `changes` as its top-level line."""
    for key, value in node_settings.checked(changes).items():
        line = f"{key} = {json.dumps(value)}"
        table = _TABLE.search(text)
        head, rest = (text[:table.start()], text[table.start():]) if table else (text, "")
        pattern = _line(key)
        if pattern.search(head):
            head = pattern.sub(line, head, count=1)
        else:
            head = (head if not head or head.endswith("\n") else head + "\n") + line + "\n"
            if rest:
                head += "\n"
        text = head + rest
    return text


def _place(path: Path) -> tuple[Path, Roots]:
    """node.toml's path spelled under its resolved grandparent, and that folder as the root."""
    root = Path(os.path.realpath(path.parent.parent))
    try:
        return root / path.parent.name / path.name, Roots((root,))
    except MuleboxError as exc:
        raise NodeFileError(f"cannot write {path}: {exc}") from exc


def read(path: Path) -> str:
    spelled, roots = _place(path)
    try:
        text = safefile.read_text(spelled, roots)
    except MuleboxError as exc:
        raise NodeFileError(f"cannot read {path}: {exc}") from exc
    if text is None:
        raise NodeFileError(f"{path} does not exist")
    return text


def apply(path: Path, changes: dict[str, Any]) -> NodeConfig:
    """Write `changes` into the node.toml at `path`; the config it now holds."""
    path = Path(path)
    text = read(path)
    try:
        new = with_settings(text, changes)
        config = node_config_from(path, tomllib.loads(new))
    except (ValueError, ConfigError) as exc:  # TOMLDecodeError is a ValueError
        raise NodeFileError(f"{path} would not read with that change: {exc}") from exc
    if new != text:
        spelled, roots = _place(path)
        mode = os.lstat(path).st_mode & 0o777
        try:
            safefile.write_text(spelled, new, roots, mode=mode)
        except (MuleboxError, OSError) as exc:
            raise NodeFileError(f"cannot write {path}: {exc}") from exc
    return config
