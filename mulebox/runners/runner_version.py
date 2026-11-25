"""The runner version isolated places build on, asked of GitHub at most once a day per node.

Every place used to ask `api.github.com` for the latest runner release when it started, without
a token. A day of deploys (a worker restart starts every place again) and the retries of failed
rounds used up GitHub's 60 requests an hour for the node's address, and from then on every round
failed with "rate limit exceeded": no place started, and the repository's CI waited
(2026-11-25). Now the answer is kept in `<cache>/actions-runner/latest.json`, shared by every
place and kept across restarts, asked again only once it is a day old, and when GitHub does not
answer the last known version is used, with a warning: a runner a few days old still takes jobs.
With none kept yet, the newest version whose place image is built on the node stands in.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from mulebox.common import safefile
from mulebox.common.log import get_logger
from mulebox.common.safepath import ensure_dir
from mulebox.runners import release
from mulebox.worker.paths import NodePaths

LOG = get_logger("runners.version")
FRESH_S = 24 * 3600.0
FILE = "latest.json"


def _file(paths: NodePaths) -> Path:
    return ensure_dir(paths.cache / release.CACHE_DIR, paths.roots) / FILE


def _read(path: Path, paths: NodePaths) -> tuple[str, float] | None:
    try:
        found = json.loads(safefile.read_text(path, paths.roots) or "")
        version, at = found["version"], float(found["at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return (version, at) if isinstance(version, str) and release.valid_version(version) else None


def known(paths: NodePaths, ask: Callable[[], str] | None = None,
          clock: Callable[[], float] = time.time,
          built: Callable[[], str | None] = lambda: None) -> str:
    """The latest runner version: the kept one while fresh, else GitHub's, else the kept one."""
    path = _file(paths)
    kept = _read(path, paths)
    now = clock()
    if kept is not None and 0 <= now - kept[1] < FRESH_S:
        return kept[0]
    try:
        version = (ask or (lambda: release.latest_release(None).version))()
    except release.ReleaseError as exc:
        if kept is None:
            stand_in = built()
            if stand_in is None or not release.valid_version(stand_in):
                raise
            LOG.warning("%s; using runner %s, the newest image built on this node", exc, stand_in)
            return stand_in
        LOG.warning("%s; using runner %s, found %.0f h ago", exc, kept[0], (now - kept[1]) / 3600)
        return kept[0]
    safefile.write_text(path, json.dumps({"version": version, "at": now}), paths.roots)
    return version
