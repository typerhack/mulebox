"""`mulebox runner caches`: a GitHub runner uses a project's mulebox package caches.

The gate (`mulebox check`) and CI on the same machine downloaded through different caches, so
a package the gate had cached could still fail to download in CI (issue #8). This points the
runner at the folders the project's own jobs use (worker/caches.py), through the same tool
settings (`npm_config_cache`, `COMPOSER_CACHE_DIR`, ...) and `MULEBOX_CACHE_<TOOL>` for a
workflow's compose file. They go in the runner's `.env`, which the runner reads when its
service starts, so the service is restarted; a runner with a job running is left alone.

Sharing means CI writes into the cache the gate reads. That is the point, and it is why only a
runner the user names gets it: a runner that builds pull requests from forks must not
(docs/install.md, Security model).
"""

from __future__ import annotations

from collections.abc import Sequence

from mulebox.common import package_cache
from mulebox.common.config_reader import NAME_RE
from mulebox.runners import layout
from mulebox.runners.manage import Machine, RunnerError
from mulebox.runners.names import RunnerUsageError, unit_name
from mulebox.worker import caches

ALL = tuple(package_cache.CAPABILITIES)
_OWN = frozenset(name for tool in caches.TOOLS for name in (tool.mount_variable, *tool.settings))


def check_tools(tools: Sequence[str]) -> tuple[str, ...]:
    unknown = [tool for tool in tools if tool not in ALL]
    if unknown:
        raise RunnerUsageError(f"unknown cache {unknown[0]!r}; one of {', '.join(ALL)}")
    return tuple(dict.fromkeys(tools)) or ALL


def share(m: Machine, name: str, project: str | None, tools: Sequence[str] = ()) -> dict[str, str]:
    """Point runner `name` at `project`'s caches (None: stop sharing), restart it; the env set."""
    folder = layout.runner_dir(m.paths, name)
    if not folder.is_dir():
        raise RunnerUsageError(f"no runner {name} on this machine; see `mulebox runner list`")
    if layout.is_busy(folder):
        raise RunnerUsageError(f"runner {name} has a job running; try again when it is idle")
    env: dict[str, str] = {}
    if project is not None:
        if not NAME_RE.fullmatch(project):
            raise RunnerUsageError(f"{project!r} is not a project name as in .mulebox.yml")
        env = caches.for_job(m.paths, project, check_tools(tools)).env
    layout.set_env(m.paths, folder, env, drop=_OWN)
    meta = layout.read_meta(folder)
    layout.write_meta(m.paths, folder, {**meta, "caches_of": project})
    proc = m.systemctl(["systemctl", "--user", "restart", unit_name(name)])
    if proc.returncode != 0:
        raise RunnerError(f"`systemctl --user restart {unit_name(name)}` failed: "
                          f"{(proc.stderr or '').strip()[-500:]}; the settings are written")
    return env
