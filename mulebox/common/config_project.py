"""Field checks that are more than a type: `compose:` and `env:` of `.mulebox.yml`, and of
node.toml `job_env`, which follows the same rules for names, `[retention]` and `[limits]`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mulebox.common import compose, env_rules, systems
from mulebox.common import isolation as isolation_rules
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
    """`job_env` of a node. It reaches compose jobs too, so their names are out."""
    return _names(reader, "job_env", reader.string_map("job_env"), True)


def retention(reader: Reader, log_default: int, step_default: int) -> dict[str, int]:
    """`[retention]` of node.toml."""
    sub = reader.table("retention")
    log_days = sub.integer("log_days", log_default, 1)
    step_days = sub.integer("step_days", max(step_default, log_days), log_days)
    sub.finish()
    return {"log_days": log_days, "step_days": step_days}


def limits(reader: Reader, idle_default: int, hours_default: int) -> dict[str, int]:
    """`[limits]` of node.toml: how long a job nobody watches may go on."""
    sub = reader.table("limits")
    idle = sub.integer("unattended_idle_min", idle_default, 1)
    hours = sub.integer("unattended_max_hours", hours_default, 1)
    sub.finish()
    if hours * 60 < idle:
        sub.fail("unattended_max_hours", "must not be shorter than unattended_idle_min")
    return {"unattended_idle_min": idle, "unattended_max_hours": hours}


def isolation_fields(reader: Reader) -> dict[str, Any]:
    level = reader.text("isolation", None)
    if level is not None and (problem := isolation_rules.level_problem(level)) is not None:
        reader.fail("isolation", problem)
    image = reader.text("image", None)
    if image is not None:
        if level != isolation_rules.CONTAINER:
            reader.fail("image", "is the image of an isolated job; it needs isolation: container")
        if (problem := isolation_rules.image_problem(image)) is not None:
            reader.fail("image", problem)
    return {"isolation": level, "image": image}


def system(reader: Reader) -> str | None:
    """`os:`: the system the project's jobs run on (common/systems.py)."""
    value = reader.text("os", None)
    if value is not None and (problem := systems.problem(value)) is not None:
        reader.fail("os", problem)
    return value
