"""Which environment names a project or a machine may set for a job.

A job's script runs `docker compose up` first, on the file the worker checked. An environment
variable is the one way a project reaches that moment: bash reads `BASH_ENV` before the script
starts, the dynamic loader reads `LD_PRELOAD` before bash does, and `COMPOSE_*` and `DOCKER_*`
pick other files, daemons or CLI plugins. Once those are refused, nothing of the project
runs before `up`. This closes that cheap route and no more: later in the job a project can
run anything, so this is no sandbox (docs/design.md, Safety).

The client checks this for a clear error; the worker checks again, since it cannot know which
client sent the job.

`${NAME}` in a value is replaced when the job starts. What it may name is settled there, as the
machine's `job_env` counts; `later_reference` and `unknown_references` are what a client can
say from the file alone. A later entry is always a mistake: entries are read in file order.
A name the file does not define may still come from the machine, so that stays a warning.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MACHINE = ("PATH", "HOME", "USER", "SHELL")
_STARTUP = ("BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS", "PS4", "IFS", "GCONV_PATH")
_STARTUP_PREFIXES = ("BASH_FUNC_",)
_LOADER = ("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH")  # others, like LD_RUN_PATH, run nothing
_COMPOSE_PREFIXES = ("COMPOSE_", "DOCKER_")
_COMPOSE_HARMLESS = ("DOCKER_BUILDKIT", "DOCKER_DEFAULT_PLATFORM")
REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SET_BY_MULEBOX = ("MULEBOX", "MULEBOX_JOB_ID", "MULEBOX_JOB_SLUG", "PATH", "UID", "GID",
                   "COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "PLAYWRIGHT_BROWSERS_PATH")
_SET_BY_MULEBOX_PREFIXES = ("MULEBOX_PORT_", "MULEBOX_CACHE_")


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


def _references(env: Mapping[str, str]) -> Iterator[tuple[int, str, str]]:
    """(place of the entry, its name, a name it uses), in file order."""
    for place, (key, value) in enumerate(env.items()):
        for name in REFERENCE.findall(value):
            yield place, key, name


def later_reference(env: Mapping[str, str]) -> tuple[str, str] | None:
    """The first (entry, name) that uses an entry further down the file, or None."""
    places = {key: place for place, key in enumerate(env)}
    for place, key, name in _references(env):
        if places.get(name, -1) > place:
            return key, name
    return None


def unknown_references(env: Mapping[str, str]) -> list[tuple[str, str]]:
    """(entry, name) for names only the build machine's `job_env` could still provide."""
    places = {key: place for place, key in enumerate(env)}
    return [(key, name) for place, key, name in _references(env)
            if places.get(name, place) >= place and name not in _SET_BY_MULEBOX
            and not name.startswith(_SET_BY_MULEBOX_PREFIXES)]
