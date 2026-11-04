"""What a job is on the wire: the argv, the environment and the `submit` body."""

from __future__ import annotations

import socket
from collections.abc import Sequence

from mulebox.client.snapshot import Snapshot
from mulebox.common import compose
from mulebox.common.config import ProjectConfig
from mulebox.common.ids import new_id

RUN_JOB_NAME = "run"


def job_request(project: ProjectConfig, target: str | Sequence[str]) -> tuple[str, list[str]]:
    """(job name, argv): a job from .mulebox.yml runs as `bash -e -c <script>`, so the first
    failing line of a multi-line job fails it, as in a GitHub Actions `run:` step."""
    if isinstance(target, str):
        return target, ["bash", "-e", "-c", project.jobs[target]]
    return RUN_JOB_NAME, list(target)


def job_env(project: ProjectConfig) -> dict[str, str]:
    """The project's `env:` values, plus the compose file list (common/compose.py)."""
    env = dict(project.env)
    if project.compose:
        env[compose.COMPOSE_FILES_KEY] = compose.join_files(project.compose)
    return env


def submit_body(project: ProjectConfig, job: str, argv: list[str], snap: Snapshot,
                detach: bool = False) -> dict:
    return {
        "project": project.project,
        "job": job,
        "argv": argv,
        "idempotency_key": new_id("sub"),
        "fingerprint": snap.fingerprint,
        "base_commit": snap.base_commit,
        "branch": snap.branch,
        "client": socket.gethostname() or "client",
        "setup": project.setup,
        "toolchain": dict(project.toolchain),
        "env": job_env(project),
        "env_order": list(project.env),  # JSON objects are sorted on the wire
        "needs": list(project.all_needs),
        "timeout_min": project.timeout_min,
        **({"detached": True} if detach else {}),
    }
