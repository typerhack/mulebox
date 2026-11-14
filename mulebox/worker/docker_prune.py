"""Docker's share of the storage cleanup, on its own with `docker_clean` (design.md, Disk use
and cleanup on its own).

Docker on a node is also its owner's, so this removes only what is surely unused:
- build cache unused for the node's `unused_days` (`builder prune --filter until=`, which goes
  by the cache's last use);
- dangling images (untagged leftovers of rebuilds) older than that;
- images mulebox's own jobs pulled and no job used for that long (image_use.py), when no
  container, running or stopped, uses them. An image mulebox never noted is never touched.
Volumes, networks and containers are never touched, nor anything through `system prune`.
"""

from __future__ import annotations

import re
import time
from typing import Any

from mulebox.worker import image_use
from mulebox.worker.docker import Docker, DockerError
from mulebox.worker.paths import NodePaths
from mulebox.worker.storage_scan import parse_size

TIMEOUT_S = 900.0
_TOTAL = re.compile(r"^\s*Total(?: reclaimed space)?:\s*(\S+)\s*$", re.IGNORECASE)
_GONE = ("No such image", "no such image")


def _freed(output: str) -> int:
    for line in reversed(output.splitlines()):
        found = _TOTAL.match(line)
        if found:
            return parse_size(found.group(1)) or 0
    return 0


def _stale_images(engine: Docker, paths: NodePaths, days: int, now: float,
                  errors: list[str]) -> tuple[int, list[str]]:
    freed, removed, gone = 0, [], []
    for image in image_use.stale(paths, days, now):
        try:
            if engine.lines("ps", "--all", "--quiet", "--filter", f"ancestor={image}"):
                continue  # a container uses it: not unused, whatever the record says
            size = int(engine.run("image", "inspect", "--format", "{{.Size}}", image).strip()
                       or 0)
            engine.run("image", "rm", image)
        except (DockerError, ValueError) as exc:
            if any(word in str(exc) for word in _GONE):
                gone.append(image)  # removed by someone else: forget it
            else:
                errors.append(f"image {image}: {exc}"[:300])
            continue
        freed += size
        removed.append(image)
    image_use.forget(paths, [*removed, *gone])
    return freed, removed


def prune(engine: Docker | None, paths: NodePaths, days: int,
          now: float | None = None) -> dict[str, Any]:
    """What it freed: {"build_cache", "images" (bytes), "removed" (image names), "error"}."""
    out: dict[str, Any] = {"build_cache": 0, "images": 0, "removed": [], "error": None}
    if engine is None:
        out["error"] = "no Docker on this node"
        return out
    now = time.time() if now is None else now
    until, errors = f"until={max(1, int(days)) * 24}h", []
    for key, args in (("build_cache", ("builder", "prune", "--force")),
                      ("images", ("image", "prune", "--force"))):
        try:
            out[key] = _freed(engine.run(*args, "--filter", until, timeout_s=TIMEOUT_S))
        except DockerError as exc:
            errors.append(str(exc)[:300])
    freed, out["removed"] = _stale_images(engine, paths, days, now, errors)
    out["images"] += freed
    out["error"] = "; ".join(errors) or None
    return out
