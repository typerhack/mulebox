"""What a worker tells the coordinator about itself with every claim.

`mulebox doctor` reads this back (`machines` request), so a project can learn before any
upload whether a machine has its toolchains. The folder scan is a few directory listings,
and a toolchain installed while the worker runs shows up on its next claim.
"""

from __future__ import annotations

from typing import Any

from mulebox.common import compose
from mulebox.common.config import NodeConfig
from mulebox.version import get_version
from mulebox.worker import toolchains
from mulebox.worker.paths import NodePaths


def by_name(paths: NodePaths) -> dict[str, list[str]]:
    """Installed toolchains as {name: [versions, oldest first]}."""
    found: dict[str, list[str]] = {}
    for name, version in toolchains.installed(paths):
        found.setdefault(name, []).append(version)
    return found


def fields(node: NodeConfig, paths: NodePaths) -> dict[str, Any]:
    """The claim body's facts about this worker."""
    return {"worker": node.name, "capabilities": compose.worker_capabilities(node.capabilities),
            "toolchains": by_name(paths), "version": get_version()}
