"""The node checks itself (design.md, A node that rests; roadmap M23.5).

Checks, each with a short time limit: free space on the disk of its roots (`min_free`), roots it
can write, `git`, the executor (systemd's user manager on Linux), Docker on a node that offers
it, Xcode on one that offers it. They run beside the worker's loop (background.py), at the
worker's start, every `EVERY_S`, every `RETRY_S` while one fails, and at once when a job could
not start or `mulebox machine check` asks (agent_health.py).

`streak`: some faults no check sees. `STREAK` jobs of two or more projects in a row that could
not start within `STREAK_S` rest the node for `REST_S`; then it takes one job at a time until a
job starts its command.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from collections.abc import Callable
from typing import Any

from mulebox.common import command, compose, isolation, node_health, units
from mulebox.common.config import NodeConfig
from mulebox.common.errors import MuleboxError
from mulebox.services.manager import service_path
from mulebox.worker.docker import Docker
from mulebox.worker import xcode as xcodes
from mulebox.worker.paths import NodePaths

EVERY_S = 300.0
RETRY_S = 60.0
TIMEOUT_S = 15.0
STREAK, STREAK_S, REST_S = 3, 900.0, 600.0

Problem = tuple[str, str, str]  # check, message, fix
Run = Callable[[list[str]], subprocess.CompletedProcess]


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return command.run(argv, timeout_s=TIMEOUT_S, env={**os.environ, "PATH": service_path()})


def disk(node: NodeConfig, paths: NodePaths) -> Problem | None:
    floor = node.storage.min_free_bytes()
    for name, path in sorted(node.roots.items()):
        try:
            free = shutil.disk_usage(path).free
        except OSError:
            continue  # `roots` says what is wrong with it
        if free < floor:
            return ("disk", f"{units.size(free)} free on the disk of its {name} folder, under "
                    f"its min_free of {units.size(floor)}",
                    f"free space on {node.name}: `mulebox storage clean` removes what its rules "
                    "allow, `mulebox project clean` lists more; `docker system df` shows Docker's")
    return None


def roots(node: NodeConfig, paths: NodePaths) -> Problem | None:
    for name in ("jobs", "projects", "staging"):
        folder = getattr(paths, name)
        try:
            with tempfile.NamedTemporaryFile(dir=folder, prefix=".mulebox-health-"):
                pass
        except OSError as exc:
            return ("roots", f"cannot write its {name} folder {folder}: {exc.strerror or exc}",
                    f"on {node.name}, make {folder} writable by the user mulebox runs as")
    return None


def git(node: NodeConfig, run: Run) -> Problem | None:
    try:
        ok = run(["git", "--version"]).returncode == 0
    except MuleboxError as exc:
        ok, detail = False, str(exc)
    else:
        detail = "it exits with an error"
    if ok:
        return None
    return ("git", f"git does not run ({detail})",
            f"install git on {node.name} (`sudo apt install git` on Ubuntu)")


def executor(node: NodeConfig, run: Run) -> Problem | None:
    """Linux jobs run as systemd user units; without the user manager none can start. Process
    groups (macOS, tests) need nothing outside the worker, so they are not checked."""
    try:
        ok = run(["systemctl", "--user", "show-environment"]).returncode == 0
    except MuleboxError:
        ok = False
    if ok:
        return None
    return ("executor", "systemd's user manager does not answer, so no job can start",
            f"on {node.name}, turn linger on for its user: `loginctl enable-linger $USER`, then "
            "`mulebox service restart worker`")


def docker(node: NodeConfig, engine: Docker, platform: str = sys.platform) -> Problem | None:
    try:
        engine.run("info", "--format", "{{.ServerVersion}}", timeout_s=TIMEOUT_S)
    except MuleboxError as exc:
        start = ("start Docker Desktop" if platform == "darwin"
                 else "start Docker: `sudo systemctl start docker`")
        return ("docker", f"Docker does not answer ({str(exc)[:120]})",
                f"{start} on {node.name}, or ask your user to; jobs without Docker still run there")
    return None


def _xcode_run(argv: list[str], developer_dir: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": service_path(), "DEVELOPER_DIR": str(developer_dir)}
    return command.run(argv, timeout_s=TIMEOUT_S, env=env)


def xcode(node: NodeConfig, run: Run | None = None,
          found: Callable[[], list[Any]] = xcodes.installed) -> Problem | None:
    """The newest Xcode found, run as jobs run it (`DEVELOPER_DIR`), not xcode-select's choice,
    which may be the Command Line Tools."""
    apps = found()
    if not apps:
        return ("xcode", "no Xcode is installed any more",
                f"install Xcode on {node.name}; jobs without Xcode still run there")
    newest = apps[-1].developer_dir
    try:
        ok = (run or (lambda argv: _xcode_run(argv, newest)))(["xcodebuild", "-version"]
                                                              ).returncode == 0
    except MuleboxError:
        ok = False
    if ok:
        return None
    return ("xcode", "xcodebuild does not run",
            f"open Xcode once on {node.name} to finish its setup, or run "
            "`sudo xcodebuild -license accept`; jobs without Xcode still run there")


def ran(offered: list[str], systemd: bool = False) -> list[str]:
    """The checks `run_all` runs on a node offering `offered`, in its order, whole-node first:
    what the dashboard lists as passing when no problem names them."""
    return ["disk", "roots", "git", *(["executor"] if systemd else []),
            *(["docker"] if compose.DOCKER_CAPABILITY in offered else []),
            *(["xcode"] if "xcode" in offered else [])]


def run_all(node: NodeConfig, paths: NodePaths, offered: list[str], engine: Docker,
            run: Run = _run, systemd: bool = False) -> list[Problem]:
    """Every failing check, whole-node ones first; `systemd`, jobs run as its user units."""
    each = {"disk": lambda: disk(node, paths), "roots": lambda: roots(node, paths),
            "git": lambda: git(node, run), "executor": lambda: executor(node, run),
            "docker": lambda: docker(node, engine),
            "xcode": lambda: xcode(node, None if run is _run else run)}
    found = [each[name]() for name in ran(offered, systemd)]
    return [item for item in found if item is not None]


class Streak:
    """Failed starts in a row; any job that starts its command ends the streak."""

    def __init__(self) -> None:
        self.failed: list[tuple[str, float]] = []  # (project, when)
        self.until: float | None = None  # resting until
        self.trial = False  # after a rest: one job at a time until one starts
        self.since: float | None = None

    def failed_start(self, project: str, now: float) -> None:
        self.failed = [(p, at) for p, at in self.failed if now - at <= STREAK_S]
        self.failed.append((project, now))
        recent = self.failed[-STREAK:]
        if self.trial or (len(recent) == STREAK and len({p for p, _ in recent}) >= 2):
            self.until, self.trial, self.since = now + REST_S, False, now
            self.failed = []

    def started(self) -> None:
        self.failed, self.trial, self.until, self.since = [], False, None, None

    def problem(self, now: float) -> Problem | None:
        if self.until is not None and now >= self.until:
            self.until, self.trial = None, True
        if self.until is None:
            return None
        return ("streak", f"{STREAK} jobs of different projects in a row could not start here",
                "read why in their logs (`mulebox logs <id> --summary`); send a job elsewhere "
                "with `--on <node>`, or wait: it takes one job again at "
                f"{node_health.clock(self.until)}")


def report(problems: list[Problem], since: dict[str, float], offered: list[str],
           streak: Streak, now: float, rounds: int = 0, floor: str = isolation.NONE,
           answers: int = 0, seen: dict[str, Any] | None = None) -> dict[str, Any]:
    """The `health` a claim and heartbeat carry; `rounds`, the checks run so far; `answers`, the
    asks of `mulebox machine check` answered. With the `container` floor every job runs in
    Docker, so Docker down rests the whole node. `seen`: what the dashboard shows beside it
    (`ran`, `checked_at`, `next_at`, `min_free`; node_health.py)."""
    items = list(problems)
    rest = streak.problem(now)
    if rest is not None:
        items.append(rest)
    checks = {check for check, _, _ in items}
    whole = set(node_health.WHOLE) | ({"docker"} if floor == isolation.CONTAINER else set())
    return {"resting": bool(checks & whole),
            "until": streak.until if rest is not None else None,
            "problems": [node_health.problem(c, m, f, since.get(c, now)) for c, m, f in items],
            "withheld": node_health.withheld_by(checks, offered), "round": rounds,
            "answers": answers, **(seen or {})}
