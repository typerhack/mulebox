"""Field checks that are more than a type: `compose:` and `env:` of `.mulebox.yml`, and
`job_env` of node.toml, which follows the same rules for names."""

from __future__ import annotations

from pathlib import Path

from mulebox.common import compose, env_rules
from mulebox.common.config_reader import Reader


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
        problem = env_rules.problem(key, for_compose)
        if problem:
            reader.fail(f"{field}.{key}", problem)
    return env


def env_values(reader: Reader, files: tuple[str, ...]) -> dict[str, str]:
    """`env:` values for the job: throwaway CI values; names checked, no overriding PATH/HOME."""
    env = _names(reader, "env", reader.string_map("env"), bool(files))
    later = env_rules.later_reference(env)
    if later:
        reader.fail(f"env.{later[0]}", f"uses ${{{later[1]}}}, which comes later in the file; "
                    f"entries are read in file order, so move {later[1]} above {later[0]}")
    return env


def job_env(reader: Reader) -> dict[str, str]:
    """`job_env` of a build machine. It reaches compose jobs too, so their names are out."""
    return _names(reader, "job_env", reader.string_map("job_env"), True)
