"""When mulebox's jobs last used each Docker image they pull, so the storage cleanup can remove
the ones no job wanted for a while, and only those (docker_prune.py; design.md, Disk use and
cleanup on its own).

Docker keeps no time of last use for an image, and an image no container uses right now is not
unused: between jobs, every base image a project pulls looks like that. So the worker notes the
images of each compose job's services (not those it builds, which go with the job) when the job
starts, in `<cache>/docker-images/used.json`. An image mulebox never noted is the node owner's, and the
cleanup never touches it.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from typing import Any

from mulebox.common import safefile
from mulebox.common.safepath import ensure_dir
from mulebox.worker.paths import NodePaths

FOLDER, FILE = "docker-images", "used.json"
MAX_IMAGES = 2000
_LOCK = threading.Lock()  # jobs start in threads of their own


def _read(paths: NodePaths) -> dict[str, float]:
    text = safefile.read_text(paths.cache / FOLDER / FILE, paths.roots)
    try:
        found = json.loads(text) if text else {}
    except ValueError:
        return {}
    return {k: float(v) for k, v in found.items()
            if isinstance(k, str) and isinstance(v, (int, float))} if isinstance(found, dict) else {}


def _write(paths: NodePaths, used: dict[str, float]) -> None:
    newest = dict(sorted(used.items(), key=lambda item: -item[1])[:MAX_IMAGES])
    folder = ensure_dir(paths.cache / FOLDER, paths.roots)
    safefile.write_text(folder / FILE, json.dumps(newest, sort_keys=True), paths.roots)


def images_of(model: dict[str, Any]) -> list[str]:
    """The images a compose model's services pull (not the ones they build)."""
    services = model.get("services") or {}
    return sorted({spec["image"] for spec in services.values()
                   if isinstance(spec, dict) and "build" not in spec
                   and isinstance(spec.get("image"), str) and spec["image"]})


def noted(paths: NodePaths, images: Iterable[str], now: float) -> None:
    images = list(images)
    if not images:
        return
    with _LOCK:
        used = _read(paths)
        used.update(dict.fromkeys(images, now))
        _write(paths, used)


def stale(paths: NodePaths, days: int, now: float) -> list[str]:
    """Images no mulebox job used for `days`, oldest first."""
    with _LOCK:
        used = _read(paths)
    return sorted((i for i, when in used.items() if now - when >= days * 86400.0),
                  key=lambda i: used[i])


def forget(paths: NodePaths, images: Iterable[str]) -> None:
    with _LOCK:
        used = _read(paths)
        for image in images:
            used.pop(image, None)
        _write(paths, used)
