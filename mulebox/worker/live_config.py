"""The worker's node.toml, followed while it runs (design.md, Node settings; M23.9).

- A change the coordinator holds for this node comes in a claim's or heartbeat's reply as
  `node_settings`; `follow` writes it into node.toml (node_file.py) and gives the new config.
- A hand edit of node.toml: `check` looks at the file's time every `CHECK_EVERY_S` and reads it
  again when it changed. A file that does not read is logged once and the old values stay.
- What applies live: `slots`, `priority`, `dev`, `capabilities` and the floor `isolation`, each counted
  from the next claim, so a running job keeps its slot and the way it was started. Any other changed field is logged as needing a restart.
- `report` is what the worker tells the coordinator with every claim and heartbeat: the settings
  it now has, and why the last change could not be written, if it could not.
"""

from __future__ import annotations

import dataclasses
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.common import node_settings
from mulebox.common.config import ConfigError, NodeConfig, load_node_config
from mulebox.common.log import get_logger
from mulebox.worker import node_file

LOG = get_logger("worker.live_config")
CHECK_EVERY_S = 2.0
LIVE = ("slots", "priority", "dev", "capabilities", "isolation")


def report(node: NodeConfig, error: str | None = None) -> dict[str, Any]:
    """The `settings` field of a claim or heartbeat."""
    return {"slots": node.slots, "priority": node.priority, "dev": node.dev,
            **({"error": error} if error else {})}


def merged(node: NodeConfig, new: NodeConfig) -> NodeConfig:
    """`node` with the fields of `new` that apply live; the rest is logged, not taken."""
    later = [f.name for f in dataclasses.fields(NodeConfig)
             if f.name not in LIVE and getattr(node, f.name) != getattr(new, f.name)]
    if later:
        LOG.warning("node.toml changed %s; that applies after `mulebox service restart worker`",
                    ", ".join(later))
    return dataclasses.replace(node, **{name: getattr(new, name) for name in LIVE})


class LiveConfig:
    def __init__(self, path: Path, clock: Callable[[], float] = time.monotonic) -> None:
        self.path, self.clock = Path(path), clock
        self.stamp = self._stamp()
        self.checked_at = clock()
        self.error: str | None = None  # why the last change from afar could not be written
        self.failed: dict[str, Any] | None = None  # that request, not tried again

    def _stamp(self) -> tuple[int, int] | None:
        try:
            info = os.stat(self.path)
        except OSError:
            return None
        return info.st_mtime_ns, info.st_size

    def check(self, node: NodeConfig) -> NodeConfig:
        """`node`, or with what a hand edit changed once the file's time moved."""
        now = self.clock()
        if now - self.checked_at < CHECK_EVERY_S:
            return node
        self.checked_at = now
        stamp = self._stamp()
        if stamp == self.stamp:
            return node
        self.stamp = stamp
        try:
            new = load_node_config(self.path)
        except (ConfigError, OSError) as exc:
            LOG.error("node.toml changed but does not read; keeping the old settings: %s", exc)
            return node
        if new.name != node.name:
            LOG.warning("node.toml names this node %s; that applies after a restart", new.name)
            return node
        updated = merged(node, new)
        if updated != node:
            LOG.info("node.toml changed: %s", _said(updated))
        return updated

    def follow(self, node: NodeConfig, body: dict[str, Any]) -> NodeConfig:
        """`node` with the change in a reply's `node_settings`, written to node.toml first."""
        wanted = body.get("node_settings")
        if not isinstance(wanted, dict) or not wanted:
            return node  # an error stays reported: the coordinator shows it only while one waits
        if all(getattr(node, key, None) == value for key, value in wanted.items()):
            return node  # already so; the next report clears it
        key = {"at": body.get("node_settings_at"), **wanted}
        if key == self.failed:
            return node
        try:
            node_settings.checked(wanted)
            new = node_file.apply(self.path, wanted)
        except (ValueError, node_file.NodeFileError) as exc:
            self.error, self.failed = str(exc), key
            LOG.error("could not apply the settings asked for: %s", exc)
            return node
        self.error = self.failed = None
        self.stamp = self._stamp()
        updated = merged(node, new)
        LOG.info("settings changed from afar: %s", _said(updated))
        return updated


def _said(node: NodeConfig) -> str:
    return (f"{node.slots} slot(s), priority {node.priority}{', dev mode' if node.dev else ''}, offers "
            f"{', '.join(node.capabilities) or 'nothing'}")
