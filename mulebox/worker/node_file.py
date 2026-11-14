"""A setting changed from afar, written into the node's own node.toml (design.md, Node settings).

Only `slots`, `priority` and `dev` (common/node_settings.py), as top-level lines: on an existing
`slots = ...` line (a bare or quoted key) only the value is replaced, its comment kept; a missing
one goes in before the first table, and every other line, comments too, stays as it was. A file
over MAX_BYTES is refused, never cut. The new text must read as a node config with the same
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

MAX_BYTES = 1 << 20  # a node.toml past this is refused rather than read in part
_TABLE = re.compile(r"^\s*\[", re.MULTILINE)
# A top-level `key = value` line; the key bare, "basic" or 'literal' (TOML's key syntax).
_KEY_LINE = re.compile(
    r"""^([ \t]*)([A-Za-z0-9_-]+|"(?:[^"\\\n]|\\.)*"|'[^'\n]*')([ \t]*=[ \t]*)(.*)$""",
    re.MULTILINE)


class NodeFileError(MuleboxError):
    """node.toml could not take the change; the message says why."""


def _key_name(spelled: str) -> str | None:
    """The key a bare or quoted spelling stands for, as TOML reads it."""
    try:
        parsed = tomllib.loads(f"{spelled} = 0")
    except ValueError:
        return None
    return next(iter(parsed)) if len(parsed) == 1 and 0 in parsed.values() else None


def _comment(value: str) -> str:
    """What follows a one-line value: the spaces and comment after it, or ""."""
    quote, i = None, 0
    while i < len(value):
        char = value[i]
        if quote:
            if char == "\\" and quote == '"':
                i += 1
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "#":
            return value[len(value[:i].rstrip()):]
        i += 1
    return ""


def _replaced(head: str, key: str, value: str) -> str | None:
    """`head` with the value on `key`'s line set to `value`, or None with no such line."""
    for match in _KEY_LINE.finditer(head):
        indent, spelled, equals, rest = match.groups()
        if _key_name(spelled) == key:
            line = f"{indent}{spelled}{equals}{value}{_comment(rest)}"
            return head[:match.start()] + line + head[match.end():]
    return None


def with_settings(text: str, changes: dict[str, Any]) -> str:
    """`text` with each of `changes` as its top-level line."""
    for key, value in node_settings.checked(changes).items():
        table = _TABLE.search(text)
        head, rest = (text[:table.start()], text[table.start():]) if table else (text, "")
        replaced = _replaced(head, key, json.dumps(value))
        if replaced is not None:
            head = replaced
        else:
            line = f"{key} = {json.dumps(value)}"
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
        text = safefile.read_text(spelled, roots, limit=MAX_BYTES + 1)
    except MuleboxError as exc:
        raise NodeFileError(f"cannot read {path}: {exc}") from exc
    if text is None:
        raise NodeFileError(f"{path} does not exist")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise NodeFileError(f"{path} is too big to change from afar (over {MAX_BYTES} bytes)")
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
