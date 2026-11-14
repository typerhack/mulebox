"""What a worker tells the coordinator about itself with every claim.

`mulebox doctor` reads this back (`machines` request), so a project can learn before any
upload whether a machine has its toolchains. The folder scan is a few directory listings,
and a toolchain installed while the worker runs shows up on its next claim.
"""

from __future__ import annotations

import sys
from typing import Any

from mulebox.common import compose, disk
from mulebox.common.config import FOUND_ON_NODE, NodeConfig
from mulebox.common.proc import HostLoad
from mulebox.version import get_version
from mulebox.worker import toolchains, xcode
from mulebox.worker.paths import NodePaths


def by_name(paths: NodePaths, platform: str = sys.platform) -> dict[str, list[str]]:
    """Installed toolchains as {name: [versions, oldest first]}; on a Mac its Xcodes too, with
    their SDKs and simulator runtimes (xcode.py)."""
    found: dict[str, list[str]] = {}
    for name, version in toolchains.installed(paths):
        found.setdefault(name, []).append(version)
    if platform == "darwin":
        found.update(xcode.report())
    return found


def fields(node: NodeConfig, paths: NodePaths, load: HostLoad | None = None) -> dict[str, Any]:
    """The claim body's facts about this worker; `load` its machine's CPU, memory and fullest disk
    (M5.3), whose free space is `disk_free` too when it read one."""
    sample = load.sample() if load is not None else None
    fullest = (sample or {}).get("disk")
    free = fullest["free"] if fullest else disk.free_bytes(node.roots.values())
    tools = by_name(paths)
    offers = compose.worker_capabilities(node.capabilities, floor=node.isolation)
    # an Xcode or a simulator runtime, as a project pinning one needs it (config.py all_needs)
    offers = list(dict.fromkeys((*offers, *(name for name in FOUND_ON_NODE if tools.get(name)))))
    return {"worker": node.name, "capabilities": offers,
            "toolchains": tools, "version": get_version(), "disk_free": free,
            **({"load": sample} if sample is not None else {})}
