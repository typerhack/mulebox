"""What a job is on the wire: the argv, the environment and the `submit` body."""

from __future__ import annotations

import platform
import socket
from collections.abc import Sequence

from mulebox.client import skill_install
from mulebox.client.snapshot import Snapshot
from mulebox.common import compose
from mulebox.common.config import ProjectConfig
from mulebox.common.config_jobs import HOST_PORTS_KEY, join_ports
from mulebox.common.ids import new_id
from mulebox.version import get_version

RUN_JOB_NAME = "run"
WARM_JOB_NAME = "warm"
WARM_ARGV = ["true"]  # everything a job has before its command, and no command


def job_request(project: ProjectConfig, target: str | Sequence[str]) -> tuple[str, list[str]]:
    """(job name, argv): a job from .mulebox.yml runs as `bash -e -c <script>`, so the first
    failing line of a multi-line job fails it, as in a GitHub Actions `run:` step."""
    if isinstance(target, str):
        return target, ["bash", "-e", "-c", project.jobs[target]]
    return RUN_JOB_NAME, list(target)


def job_env(project: ProjectConfig) -> dict[str, str]:
    """The project's `env:` values, plus the compose file list (common/compose.py) and the
    names of the job's own ports (config_jobs.py)."""
    env = dict(project.env)
    if project.compose:
        env[compose.COMPOSE_FILES_KEY] = compose.join_files(project.compose)
    if project.host_ports:
        env[HOST_PORTS_KEY] = join_ports(project.host_ports)
    return env


_OS_NAMES = {"Darwin": "macOS"}


def client_os() -> str:
    """The laptop's system as people name it, for the dashboard: macOS, Linux, Windows."""
    system = platform.system() or "unknown"
    return _OS_NAMES.get(system, system)


def submit_body(project: ProjectConfig, job: str, argv: list[str], snap: Snapshot,
                detach: bool = False, reuse: bool = False, take: tuple[str, ...] = ()) -> dict:
    return {
        "project": project.project,
        "job": job,
        "argv": argv,
        "idempotency_key": new_id("sub"),
        "fingerprint": snap.fingerprint,
        "base_commit": snap.base_commit,
        "branch": snap.branch,
        "client": socket.gethostname() or "client",
        "client_os": client_os(),
        "client_version": get_version(),
        "skill": skill_install.state_here(),
        "setup": project.setup,
        "install": project.install,
        "toolchain": dict(project.toolchain),
        "env": job_env(project),
        "env_order": list(project.env),  # JSON objects are sorted on the wire
        "needs": list(project.all_needs),
        "timeout_min": project.timeout_min,
        **({"detached": True} if detach else {}),
        **({"reuse": True} if reuse else {}),
        **({"take": list(take)} if take else {}),
    }
