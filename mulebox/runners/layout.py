"""Files mulebox keeps in a runner folder `<runners>/<name>/` (docs/interfaces-m3.md).

- `mulebox-hooks/started.sh` and `completed.sh`: the job hooks GitHub's runner calls; each
  execs `~/.mulebox/bin/mulebox runner-hook <started|completed>`.
- `.env`: the runner's own environment file (written by its `config.sh`); mulebox sets
  `ACTIONS_RUNNER_HOOK_JOB_STARTED` and `ACTIONS_RUNNER_HOOK_JOB_COMPLETED` in it, and the cache
  settings of `runner caches` (runner_caches.py), and keeps every other line.
- `.mulebox-runner.json`: what `runner add` registered (repo, labels, version), for
  `runner list` and `runner remove --repo`.
- `.mulebox-reservation`: written by the hooks while a job holds a build slot (busy).

Every file is written to a temporary name in the same folder and renamed into place.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mulebox.common import safefile
from mulebox.common.safepath import ensure_dir
from mulebox.runners.names import RunnerUsageError, check_name
from mulebox.worker.paths import NodePaths

HOOKS_DIR = "mulebox-hooks"
HOOKS = {"started": "ACTIONS_RUNNER_HOOK_JOB_STARTED",
         "completed": "ACTIONS_RUNNER_HOOK_JOB_COMPLETED"}
ENV_FILE = ".env"
META_FILE = ".mulebox-runner.json"
RESERVATION_FILE = ".mulebox-reservation"
HOOK_SCRIPT = """#!/bin/sh
# Installed by `mulebox runner add`: GitHub job-{kind} hook (reserves the build slot).
exec "$HOME/.mulebox/bin/mulebox" runner-hook {kind}
"""
# The started hook fails closed: a failed hook alone lets the job's `if: always()` steps run.
# The guard (guard.py) kills the job's runner process itself when it refuses; this covers mulebox
# failing in any other way, even failing to start: the job's runner process, this script's
# parent, is killed. A parent it cannot tell is the runner's is waited out instead: the job
# stays in the hook until GitHub ends it, and the script ends with it.
STARTED_SCRIPT = """#!/bin/sh
# Installed by `mulebox runner add`: GitHub job-started hook (the guard, then the build slot).
"$HOME/.mulebox/bin/mulebox" runner-hook started && exit 0
parent=$(tr '\\000' ' ' 2>/dev/null < "/proc/$PPID/cmdline" || ps -o command= -p "$PPID" 2>/dev/null)
case "$parent" in
  *Runner.Worker*) kill -9 "$PPID"; exit 1 ;;
esac
while kill -0 "$PPID" 2>/dev/null; do sleep 2; done
exit 1
"""
# The unit template (install/systemd/mulebox-runner@.service) runs %h/.mulebox/runners/%i.
UNIT_RUNNERS = Path(".mulebox") / "runners"


def runner_dir(paths: NodePaths, name: str) -> Path:
    return paths.runners / check_name(name)


def check_unit_root(paths: NodePaths, home: Path | None = None) -> None:
    """The unit template only knows ~/.mulebox/runners; refuse another runners root."""
    expected = Path(os.path.realpath((home or Path.home()) / UNIT_RUNNERS))
    if paths.runners != expected:
        raise RunnerUsageError(
            f"the runners root is {paths.runners}, but mulebox-runner@.service runs runners "
            f"from {expected}; set roots.runners to {expected} in node.toml")


def write_file(paths: NodePaths, path: Path, text: str, mode: int = 0o640) -> None:
    """Write text atomically next to path (the folder must exist inside the roots)."""
    safefile.write_text(path, text, paths.roots, mode)


def write_hooks(paths: NodePaths, folder: Path) -> dict[str, Path]:
    """Write both hook scripts; return {env variable: script path}."""
    hooks = ensure_dir(folder / HOOKS_DIR, paths.roots)
    scripts = {}
    for kind, variable in HOOKS.items():
        script = hooks / f"{kind}.sh"
        text = STARTED_SCRIPT if kind == "started" else HOOK_SCRIPT.format(kind=kind)
        write_file(paths, script, text, 0o750)
        scripts[variable] = script
    return scripts


def set_env_hooks(paths: NodePaths, folder: Path, scripts: dict[str, Path]) -> None:
    """Set the hook variables in the runner's .env; other lines are kept."""
    set_env(paths, folder, {name: str(script) for name, script in scripts.items()})


def set_env(paths: NodePaths, folder: Path, values: dict[str, str],
            drop: frozenset[str] = frozenset()) -> None:
    """Set `values` in the runner's .env, removing the names in `drop` first; other lines kept."""
    env = folder / ENV_FILE
    try:
        lines = env.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    gone = drop | values.keys()
    kept = [ln for ln in lines if ln.split("=", 1)[0].strip() not in gone]
    kept += [f"{name}={value}" for name, value in values.items()]
    write_file(paths, env, "\n".join(kept) + "\n")


def write_meta(paths: NodePaths, folder: Path, info: dict[str, Any]) -> None:
    write_file(paths, folder / META_FILE, json.dumps(info, indent=2, sort_keys=True) + "\n")


def read_meta(folder: Path) -> dict[str, Any]:
    """The runner's metadata, or {} when missing or unreadable."""
    try:
        data = json.loads((folder / META_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def runner_folders(paths: NodePaths) -> list[Path]:
    """Runner folders (hidden temporary folders skipped), sorted by name."""
    if not paths.runners.is_dir():
        return []
    return sorted(p for p in paths.runners.iterdir()
                  if p.is_dir() and not p.is_symlink() and not p.name.startswith("."))


def is_busy(folder: Path) -> bool:
    return (folder / RESERVATION_FILE).exists()
