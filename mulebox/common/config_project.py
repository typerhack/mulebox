"""Field checks that are more than a type: `compose:` and `env:` of `.mulebox.yml`, and
`job_env` of node.toml, which follows the same rules for names."""

from __future__ import annotations

import re
from pathlib import Path

from mulebox.common import compose
from mulebox.common.config_reader import Reader

_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ENV_RESERVED = ("PATH", "HOME", "USER", "SHELL")


def compose_files(reader: Reader, project_dir: Path, project_file: str) -> tuple[str, ...]:
    """`compose:` files: safe names, no repeats, and present in the project."""
    files = reader.strings("compose")
    for index, name in enumerate(files):
        where = f"compose[{index}]"
        problem = compose.file_problem(name)
        if problem:
            reader.fail(where, problem)
        if name in files[:index]:
            reader.fail(where, f"lists {name} twice")
        if not (project_dir / name).is_file():
            reader.fail(where, f"file {name} not found next to {project_file}")
    return files


def _names(reader: Reader, field: str, env: dict[str, str], for_compose: bool) -> dict[str, str]:
    for key in env:
        if not _ENV_NAME.fullmatch(key):
            reader.fail(f"{field}.{key}", "must be a shell variable name (letters, digits, _)")
        if key in _ENV_RESERVED or key.startswith("MULEBOX"):
            reader.fail(f"{field}.{key}",
                        "is set by mulebox or the build machine; choose another name")
        if for_compose and key in compose.RESERVED_ENV:
            reader.fail(f"{field}.{key}", "is set by mulebox for a compose: project; remove it")
    return env


def env_values(reader: Reader, files: tuple[str, ...]) -> dict[str, str]:
    """`env:` values for the job: throwaway CI values; names checked, no overriding PATH/HOME."""
    return _names(reader, "env", reader.string_map("env"), bool(files))


def job_env(reader: Reader) -> dict[str, str]:
    """`job_env` of a build machine. It reaches compose jobs too, so their names are out."""
    return _names(reader, "job_env", reader.string_map("job_env"), True)
