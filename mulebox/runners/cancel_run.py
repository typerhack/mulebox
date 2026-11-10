"""Cancel a GitHub run from the dashboard: `gh run cancel <id> -R <owner/repo>` on its machine.

GitHub owns the run, so mulebox asks GitHub to cancel it; the runner then stops the job and its
completed hook frees the slot as usual. The repository and run id come from the slot's run
address (hooks.GitHubJob.run_url) and are checked before they reach an argv. `gh` must be
logged in on the machine the dashboard runs on, with rights to cancel runs in the repository.
"""

from __future__ import annotations

import re

from mulebox.common.redact import Redactor
from mulebox.runners.github import GhRun, GitHubError, run_gh
from mulebox.runners.names import RunnerUsageError, check_repo

_RUN_URL = re.compile(r"https://github\.com/([^/]+/[^/]+)/actions/runs/([0-9]{1,20})(?:/.*)?")


def run_of(run_url: object) -> tuple[str, str]:
    """`(owner/repo, run id)` from a run address on github.com; GitHubError otherwise."""
    found = _RUN_URL.fullmatch(run_url) if isinstance(run_url, str) else None
    if found is None:
        raise GitHubError("this slot has no GitHub run address to cancel; cancel it on GitHub")
    try:
        return check_repo(found.group(1)), found.group(2)
    except RunnerUsageError as exc:
        raise GitHubError(str(exc)) from None


def cancel_run(run_url: object, run: GhRun = run_gh) -> str:
    """Ask GitHub to cancel the run; its `owner/repo#id` on success, GitHubError otherwise."""
    repo, run_id = run_of(run_url)
    proc = run(["gh", "run", "cancel", run_id, "-R", repo])
    if proc.returncode != 0:
        detail = Redactor([]).redact((proc.stderr or proc.stdout or "").strip())[-300:]
        hint = (" Log `gh` in on the build machine: gh auth login"
                if "auth" in detail.lower() or "token" in detail.lower() else "")
        raise GitHubError(f"GitHub did not cancel run {run_id} of {repo}: "
                          f"{detail or 'no output'}.{hint}")
    return f"{repo}#{run_id}"
