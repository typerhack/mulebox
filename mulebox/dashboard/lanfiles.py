"""Where `lan` mode keeps its private files, and how they are written.

The certificate, its key and the password hash sit in `dashboard/` beside node.toml, not
in a mulebox root: they are the operator's configuration, not job data, and jobs never
touch them. Only the explicit `mulebox dashboard cert` and `password` commands write
here, and neither deletes anything but its own temporary file.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from mulebox.common.config import node_config_path
from mulebox.common.errors import MuleboxError


class LanNotReady(MuleboxError):
    """`lan` mode cannot start: the message says which setup step is missing."""


def lan_dir(config_path: Path | None = None) -> Path:
    """The private folder for this node's config file."""
    path = Path(config_path) if config_path is not None else node_config_path()
    return path.parent / "dashboard"


def ensure_private_dir(directory: Path) -> Path:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    return directory


def write_private(path: Path, text: str) -> None:
    """Replace `path` atomically with a file only this user can read."""
    ensure_private_dir(path.parent)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
