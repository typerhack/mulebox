"""A mulebox result on GitHub as a commit status (M24.6, design.md, Results on GitHub).

With `github_status: true` in `.mulebox.yml`, `mulebox check` posts its result to the commit it
ran on, as the status `mulebox/<job>`, so a pull request shows it and it can be a required check.
Only when the files sent are exactly a pushed commit: the worktree is clean (no change, no
untracked file) and a remote-tracking branch holds HEAD. Anything else posts nothing and says
why, as a status on a commit must be about that commit's files. It goes out from the dev machine
through its own `gh`, so nothing reaches in to the node. Settled before the job is sent, as the
files may change while it runs.

The status is `success` for exit 0, `error` when the job gave no verdict (it could not start,
was cancelled, interrupted, stopped, or mulebox itself failed), else `failure`.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from mulebox.client import gitinfo
from mulebox.client import report as rpt
from mulebox.common.config import ProjectConfig

NO_VERDICT = {rpt.EXIT_USAGE, rpt.EXIT_UNREACHABLE, rpt.EXIT_REMOTE, rpt.EXIT_NOT_STARTED,
              rpt.EXIT_INTERRUPTED, rpt.EXIT_STOPPED, rpt.EXIT_TIMED_OUT, rpt.EXIT_CANCELLED}
Run = Callable[[list[str], Path], subprocess.CompletedProcess]


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False)


def pushed_commit(root: Path, run: Run = _run) -> tuple[str | None, str]:
    """(the commit the files are, or None, and why not)."""
    status = run(["git", "status", "--porcelain", "--untracked-files=normal"], root)
    if status.returncode != 0:
        return None, "git could not say whether the worktree is clean"
    if status.stdout.strip():
        return None, "the worktree has changes not in a commit"
    head = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    if not head:
        return None, "there is no commit yet"
    remote = run(["git", "branch", "--remotes", "--contains", head], root)
    if remote.returncode != 0 or not remote.stdout.strip():
        return None, "the commit is not pushed (no remote-tracking branch holds it)"
    return head, ""


def state_for(code: int) -> str:
    if code == 0:
        return "success"
    return "error" if code in NO_VERDICT else "failure"


def post(root: Path, commit: str, job: str, code: int, run: Run = _run) -> tuple[bool, str]:
    """Post the status through the dev machine's `gh`; (posted, gh's complaint)."""
    state = state_for(code)
    words = {"success": "passed", "failure": f"failed (exit {code})",
             "error": f"gave no result (exit {code})"}[state]
    proc = run(["gh", "api", "-X", "POST", f"repos/{{owner}}/{{repo}}/statuses/{commit}",
                "-f", f"state={state}", "-f", f"context=mulebox/{job}",
                "-f", f"description=mulebox {job} {words}"], root)
    return proc.returncode == 0, (proc.stderr or "").strip()[-300:]


def before(root: Path, out: TextIO, run: Run = _run) -> str | None:
    """The commit to report on, or None with a note on `out`."""
    try:
        commit, why = pushed_commit(root, run)
    except (OSError, gitinfo.GitError) as exc:
        commit, why = None, str(exc)
    if commit is None:
        out.write(f"mulebox: no GitHub status for this run: {why}\n")
    return commit


def after(root: Path, commit: str, job: str, code: int, out: TextIO, run: Run = _run) -> None:
    try:
        posted, detail = post(root, commit, job, code, run)
    except OSError as exc:
        posted, detail = False, str(exc)
    if posted:
        out.write(f"mulebox: GitHub status mulebox/{job} set to {state_for(code)} on "
                  f"{commit[:12]}\n")
    else:
        out.write(f"mulebox: could not set the GitHub status ({detail or 'gh failed'}); "
                  "is `gh` signed in with access to this repository?\n")


def around(project: ProjectConfig, root: Path, job: str, detach: bool, out: TextIO,
           go: Callable[[], int], run: Run = _run) -> int:
    """Run the job through `go`, posting its status when the project asks and it can."""
    commit = None
    if project.github_status and detach:
        out.write("mulebox: no GitHub status with --detach: nothing is here to post it at the "
                  "end\n")
    elif project.github_status:
        commit = before(root, out, run)
    code = go()
    if commit is not None:
        after(root, commit, job, code, out, run)
    return code
