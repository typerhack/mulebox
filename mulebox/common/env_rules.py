"""Which environment names a project or a machine may set for a job.

A job's script runs `docker compose up` first, on the file the worker checked. An environment
variable is the one way a project reaches that moment: bash reads `BASH_ENV` before the script
starts, the dynamic loader reads `LD_PRELOAD` before bash does, and `COMPOSE_*` and `DOCKER_*`
pick other files, daemons or CLI plugins. Once those are refused, nothing of the project
runs before `up`. This closes that cheap route and no more: later in the job a project can
run anything, so this is no sandbox (docs/design.md, Safety).

The client checks this for a clear error; the worker checks again, since it cannot know which
client sent the job.
"""

from __future__ import annotations

import re

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MACHINE = ("PATH", "HOME", "USER", "SHELL")
_STARTUP = ("BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS", "PS4", "IFS", "GCONV_PATH")
_STARTUP_PREFIXES = ("BASH_FUNC_",)
_LOADER = ("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH")  # others, like LD_RUN_PATH, run nothing
_COMPOSE_PREFIXES = ("COMPOSE_", "DOCKER_")
_COMPOSE_HARMLESS = ("DOCKER_BUILDKIT", "DOCKER_DEFAULT_PLATFORM")


def problem(name: str, for_compose: bool) -> str | None:
    """Why `name` cannot be set for a job, or None. `for_compose`: a `compose:` project."""
    if not _NAME.fullmatch(name):
        return "must be a shell variable name (letters, digits, _)"
    if name in _MACHINE or name.startswith("MULEBOX"):
        return "is set by mulebox or the build machine; choose another name"
    if name in _STARTUP or name.startswith(_STARTUP_PREFIXES):
        return "changes how the job's shell starts, so a job may not set it"
    if for_compose and name in _LOADER:
        return "changes what runs before Docker Compose starts, so a compose: project may not set it"
    if for_compose and name.startswith(_COMPOSE_PREFIXES) and name not in _COMPOSE_HARMLESS:
        return "changes how Docker Compose starts, and mulebox sets that for a compose: project"
    return None
