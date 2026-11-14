"""The folder name of a branch in a project's folder on a node (design.md, Project folders):
the branch's own name made safe for a folder, and a hash, so `a/b` and `a-b` stay apart. One
rule for the worker that makes the folders (worker/project_home.py) and the coordinator that
names them back (coordinator/storage.py).
"""

from __future__ import annotations

import hashlib
import re

NO_BRANCH = "detached"
_NOT_A_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def slug(branch: str | None) -> str:
    """A folder name for `branch`."""
    if not branch:
        return NO_BRANCH
    name = _NOT_A_NAME.sub("-", branch).strip("-.") or "branch"
    return f"{name[:60]}-{hashlib.sha256(branch.encode()).hexdigest()[:8]}"
