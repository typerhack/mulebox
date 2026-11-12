"""One-job runners from GitHub for an isolated runner, through the node's own `gh`.

`generate-jitconfig` registers a runner that takes exactly one job and is removed by GitHub
after it; its configuration (credentials included) goes to the container on stdin, never in
an argument or a file. Only an admin of the repository may make one, so the node's `gh` must
be signed in as one (docs/install.md, What a runner needs on GitHub). A runner made but never
given a job is deleted here when its container stops.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from mulebox.common import download
from mulebox.common.redact import Redactor
from mulebox.runners.github import GhRun, GitHubError, run_gh
from mulebox.runners.names import check_repo

BASE_LABELS = ("self-hosted", "Linux")
_ARCH_LABELS = {"x64": "X64", "arm64": "ARM64"}
_SUFFIX = re.compile(r"[0-9a-z]{8}")


def arch_label() -> str:
    """The label GitHub gives a runner on this machine's processor."""
    return _ARCH_LABELS.get(download.cpu_arch(), "X64")


@dataclass(frozen=True)
class JitRunner:
    id: int
    name: str
    config: str


def create(repo: str, name: str, labels: Sequence[str], run: GhRun = run_gh) -> JitRunner:
    argv = ["gh", "api", "-X", "POST",
            f"repos/{check_repo(repo)}/actions/runners/generate-jitconfig",
            "-f", f"name={name}", "-F", "runner_group_id=1", "-f", "work_folder=_work"]
    for label in dict.fromkeys([*BASE_LABELS, *labels]):
        argv += ["-f", f"labels[]={label}"]
    proc = run(argv)
    try:
        data = json.loads(proc.stdout or "")
        made = JitRunner(int(data["runner"]["id"]), name, str(data["encoded_jit_config"]))
    except (ValueError, KeyError, TypeError):
        made = None
    if proc.returncode != 0 or made is None or not made.config:
        secret = [made.config] if made else []
        detail = Redactor(secret).redact((proc.stderr or "").strip())[-500:]
        raise GitHubError(f"gh could not make a one-job runner for {repo}: "
                          f"{detail or 'no output'}. The node's `gh` must be signed in as an "
                          "admin of the repository (`gh auth login` on the node)")
    return made


def delete(repo: str, runner_id: int, run: GhRun = run_gh) -> bool:
    """Remove a one-job runner that never got its job; False when GitHub did not."""
    proc = run(["gh", "api", "-X", "DELETE",
                f"repos/{check_repo(repo)}/actions/runners/{int(runner_id)}"])
    return proc.returncode == 0


def runner_name(place: str, suffix: str) -> str:
    """A one-job runner's name: its place's, a dash and 8 letters or digits (one per round)."""
    if not _SUFFIX.fullmatch(suffix):
        raise ValueError(f"a one-job runner's suffix is 8 lower-case letters or digits: {suffix!r}")
    return f"{place}-{suffix}"


def ids_of(repo: str, place: str, run: GhRun = run_gh) -> list[int]:
    """The ids of this place's one-job runners on GitHub, by exact name: those of a place
    named `build-fast` are never taken for those of `build`."""
    own = re.compile(re.escape(place) + "-" + _SUFFIX.pattern)
    proc = run(["gh", "api", "--paginate", f"repos/{check_repo(repo)}/actions/runners",
                "--jq", ".runners[] | \"\\(.id) \\(.name)\""])
    found = []
    for line in (proc.stdout or "").splitlines() if proc.returncode == 0 else ():
        runner_id, _, name = line.partition(" ")
        if own.fullmatch(name) and runner_id.isdigit():
            found.append(int(runner_id))
    return found


def admin(repo: str, run: GhRun = run_gh) -> tuple[bool, str]:
    """(is `gh` here an admin of repo, the repository's visibility)."""
    proc = run(["gh", "api", f"repos/{check_repo(repo)}",
                "--jq", '"\\(.permissions.admin) \\(.visibility)"'])
    parts = (proc.stdout or "").split()
    if proc.returncode != 0 or len(parts) != 2:
        raise GitHubError(f"gh on the node cannot read {repo}: "
                          f"{(proc.stderr or '').strip()[-300:] or 'no output'}; run "
                          "`gh auth login` on the node as an admin of the repository")
    return parts[0] == "true", parts[1]
