"""The worker's word that it reached its coordinator, for an upgrade's trial (services/trial.py).

Once per process, after the first reply that is no error, the worker writes its version and pid to
`<staging>/worker-state/contact`. The trial of an upgrade waits for that file to name the new
version: a worker that runs but cannot talk to its coordinator does not pass.
"""

from __future__ import annotations

import json
import os
import time

from mulebox.common import safefile
from mulebox.common.safepath import ensure_dir
from mulebox.version import get_version
from mulebox.worker.paths import NodePaths

FOLDER, FILE = "worker-state", "contact"


def path(paths: NodePaths):
    return paths.staging / FOLDER / FILE


def record(paths: NodePaths, now: float | None = None) -> None:
    marker = path(paths)
    ensure_dir(marker.parent, paths.roots)
    said = {"version": get_version(), "pid": os.getpid(), "at": time.time() if now is None else now}
    safefile.write_text(marker, json.dumps(said) + "\n", paths.roots, 0o600)


def read(paths: NodePaths) -> dict | None:
    text = safefile.read_text(path(paths), paths.roots)
    try:
        said = json.loads(text) if text else None
    except ValueError:
        return None
    return said if isinstance(said, dict) else None
