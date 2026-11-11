"""Executor that runs each job as a transient systemd user unit (Linux nodes).

The unit is `mulebox-job-<job_id>`, with a runtime limit only if the job has one, `KillMode=control-group` (stopping
it kills the whole process tree) and lower CPU and IO weights. Output is appended to the
job's `out.log`. Environment values are passed as separate `--setenv=K=V` arguments; no
shell ever sees them.

systemd expands `${NAME}` in a unit's command line itself, inside a long argument as well,
before bash sees the script: `${x}` of a variable the script sets, `${NAME:-default}` and
`${list[1]}` all came out empty, and `$$` lost a dollar. So `run_argv` doubles every `$`, which
systemd reads back as one, and a job's script reaches bash exactly as written.

Reading the result: the unit is started without `--collect`. A unit whose main process
exits 0 becomes inactive and is unloaded at once (`LoadState=not-found`); a non-zero exit,
a signal or the runtime limit leaves it `failed` with `Result=` and `ExecMain*` set until
`reset-failed`, which this executor calls after reading it. With `--collect` a failed unit
would be unloaded as well, and exit codes and timeouts could not be told apart from
success. Every name this executor touches starts with `mulebox-job-`.
"""

from __future__ import annotations

import math
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from mulebox.worker.executor import UNIT_PREFIX, ExecutorError, RunSpec

SYSTEMCTL_TIMEOUT_S = 60
_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_UNIT_RE = re.compile(re.escape(UNIT_PREFIX) + r"[A-Za-z0-9-]+")
SHOW_PROPERTIES = ("LoadState", "ActiveState", "SubState", "Result", "ExecMainCode",
                   "ExecMainStatus")
CLD_KILLED, CLD_DUMPED = 2, 3

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


def default_runner(argv: Sequence[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(list(argv), capture_output=True, text=True,
                              timeout=SYSTEMCTL_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExecutorError(f"`{' '.join(argv[:3])}` failed: {exc}") from exc


def _check_unit(name: str) -> str:
    if not _UNIT_RE.fullmatch(name):
        raise ExecutorError(f"refusing unit name {name!r}: not a {UNIT_PREFIX}* unit")
    return name


def run_argv(spec: RunSpec) -> list[str]:
    """The exact `systemd-run` command for spec (docs/interfaces-m1.md, Worker)."""
    unit = _check_unit(spec.name)
    for path in (spec.log_path, spec.cwd):
        if any(c.isspace() for c in str(path)):
            raise ExecutorError(f"path {path} contains whitespace; systemd cannot use it")
    limit = [] if spec.timeout_s is None else [
        f"--property=RuntimeMaxSec={max(1, math.ceil(spec.timeout_s))}"]
    argv = [
        "systemd-run", "--user", f"--unit={unit}", *limit,
        "--property=KillMode=control-group",
        "--property=TimeoutStopSec=10s",
        "--property=CPUWeight=50",
        "--property=IOWeight=50",
        f"--property=StandardOutput=append:{spec.log_path}",
        f"--property=StandardError=append:{spec.log_path}",
        f"--working-directory={spec.cwd}",
    ]
    for key, value in spec.env.items():
        if not _ENV_KEY.fullmatch(key) or "\0" in value:
            raise ExecutorError(f"invalid environment variable {key!r}")
        argv.append(f"--setenv={key}={value}")
    return [*argv, "--", *(arg.replace("$", "$$") for arg in spec.argv)]


def parse_show(text: str) -> dict[str, str]:
    """Parse `systemctl show` output (`Key=Value` lines)."""
    props = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            props[key.strip()] = value.strip()
    return props


def exit_from_props(props: dict[str, str]) -> tuple[int | None, bool]:
    """(exit code or None while running, timed_out) from the unit's properties."""
    load, active = props.get("LoadState", ""), props.get("ActiveState", "")
    if load == "not-found" or active == "inactive":
        return 0, False
    if active != "failed":
        return None, False  # active, activating, deactivating, reloading
    timed_out = props.get("Result") == "timeout"
    try:
        status = int(props.get("ExecMainStatus", ""))
        code = int(props.get("ExecMainCode", "1"))
    except ValueError:
        return 1, timed_out
    if code in (CLD_KILLED, CLD_DUMPED):
        return 128 + status, timed_out
    return (status if status else 1), timed_out


@dataclass
class UnitHandle:
    name: str
    exit_code: int | None = None
    timed_out: bool = False


class SystemdExecutor:
    def __init__(self, runner: Runner = default_runner) -> None:
        self._run = runner

    def _systemctl(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        proc = self._run(["systemctl", "--user", *args])
        if check and proc.returncode != 0:
            raise ExecutorError(f"systemctl --user {args[0]} failed: {(proc.stderr or '').strip()}")
        return proc

    def start(self, spec: RunSpec) -> UnitHandle:
        proc = self._run(run_argv(spec))
        if proc.returncode != 0:
            raise ExecutorError(f"systemd-run failed for {spec.name}: {(proc.stderr or '').strip()}")
        return UnitHandle(spec.name)

    def poll(self, handle: UnitHandle) -> int | None:
        if handle.exit_code is not None:
            return handle.exit_code
        props = parse_show(self._systemctl(
            "show", handle.name, *(f"--property={p}" for p in SHOW_PROPERTIES)).stdout)
        code, timed_out = exit_from_props(props)
        if code is None:
            return None
        handle.exit_code, handle.timed_out = code, timed_out
        self._systemctl("reset-failed", handle.name, check=False)
        return code

    def timed_out(self, handle: UnitHandle) -> bool:
        return handle.timed_out

    def stop(self, handle: UnitHandle) -> None:
        self.kill(handle.name)
        if handle.exit_code is None:
            handle.exit_code = 143

    def systemctl(self, *args: str) -> subprocess.CompletedProcess:
        """`systemctl --user` for other mulebox units (runners/runner_controls.py checks names)."""
        return self._systemctl(*args)

    def freeze(self, handle: UnitHandle, on: bool) -> None:
        """Freeze or thaw the unit's processes (cgroup freezer); a stop thaws it by itself."""
        self._systemctl("freeze" if on else "thaw", _check_unit(handle.name))

    def prioritize(self, handle: UnitHandle, on: bool) -> None:
        """The unit's CPU and disk weight: the top while boosted, its usual share otherwise."""
        weight = 10000 if on else 50
        self._systemctl("set-property", "--runtime", _check_unit(handle.name),
                        f"CPUWeight={weight}", f"IOWeight={weight}")

    def list_orphans(self) -> list[str]:
        proc = self._systemctl("list-units", "--all", "--plain", "--no-legend",
                               "--type=service", f"{UNIT_PREFIX}*")
        names = []
        for line in proc.stdout.splitlines():
            words = [w for w in line.split() if w not in ("*", "●")]  # failed-unit dot
            name = words[0].removesuffix(".service") if words else ""
            if _UNIT_RE.fullmatch(name):
                names.append(name)
        return sorted(set(names))

    def kill(self, name: str) -> None:
        """Stop the unit (SIGTERM, SIGKILL after TimeoutStopSec) and forget a failed state."""
        _check_unit(name)
        self._systemctl("stop", name, check=False)
        self._systemctl("reset-failed", name, check=False)
