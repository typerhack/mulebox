"""Issue drafts about what mulebox could not handle (docs/design.md, Agent feedback).

`draft` builds markdown and prints it; nothing leaves the machine. `post` sends a file
only if it passes the scrub again unchanged, so what was reviewed is what is sent and
nothing private can be added on the way. A draft holds the summary, the mulebox version,
the operating system and the job's result. Never a project, branch, machine or command;
log lines only when asked for, and scrubbed like everything else.
"""

from __future__ import annotations

import getpass
import platform
import re
import socket
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from mulebox.client import gitinfo
from mulebox.common.anonymize import Anonymizer
from mulebox.common.config import ClientConfig, ProjectConfig
from mulebox.common.errors import MuleboxError

TITLE_CHARS = 100
LOG_LINES = 40
LOG_CHARS = 4000
NAME_FIELDS = ("project", "branch", "client", "worker")
RESULT_FIELDS = ("state", "outcome", "exit_code", "duration_s")
_REPO_IN_URL = re.compile(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$")


class FeedbackError(MuleboxError):
    """A draft that cannot be made or sent."""


def _safe_call(call: Callable[[], str]) -> str:
    try:
        return call()
    except (MuleboxError, OSError, KeyError):
        return ""


def local_names(project: ProjectConfig | None, root: Path | None,
                config: ClientConfig | None) -> set[str]:
    """Names on this machine that would identify the user or the project."""
    names = {_safe_call(getpass.getuser), _safe_call(socket.gethostname)}
    names.add(_safe_call(socket.gethostname).split(".")[0])
    if config is not None:
        names.add(config.coordinator)
    if project is not None:
        names.add(project.project)
    if root is not None:
        names |= {root.name, _safe_call(lambda: gitinfo.branch(root))}
        names |= {_safe_call(lambda: gitinfo.config_value(root, key))
                  for key in ("user.name", "user.email")}
        match = _REPO_IN_URL.search(_safe_call(lambda: gitinfo.remote_url(root)))
        if match:
            names |= {match[1], match[2], f"{match[1]}/{match[2]}"}
    return {name for name in names if name}


def names_in(jobs: Iterable[dict[str, Any]]) -> set[str]:
    """Every project, branch and machine the coordinator knows, not just this project's."""
    return {str(job[field]) for job in jobs for field in NAME_FIELDS if job.get(field)}


def tail(log: str) -> str:
    return "\n".join(log.splitlines()[-LOG_LINES:])[-LOG_CHARS:]


def title_from(summary: str) -> str:
    """The first line, whatever punctuation it holds, cut only if too long and then at a word."""
    line = summary.strip().splitlines()[0]
    if len(line) <= TITLE_CHARS:
        return line
    return line[:TITLE_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:") or line[:TITLE_CHARS]


def draft(summary: str, version: str, anonymizer: Anonymizer,
          job: dict[str, Any] | None = None, log: str | None = None) -> str:
    title = title_from(summary)
    lines = [f"# {title}", "", "## What happened", "", summary.strip(), "", "## Environment", "",
             f"- mulebox {version}",
             f"- laptop: {platform.system()}, Python {platform.python_version()}"]
    if job is not None:
        lines += ["", "## Job", ""]
        lines += [f"- {name}: {job.get(name)}" for name in RESULT_FIELDS
                  if job.get(name) is not None]
    if log:
        lines += ["", f"## Last {LOG_LINES} log lines at most", "", "```", tail(log), "```"]
    return anonymizer.scrub("\n".join(lines)) + "\n"


def check_clean(text: str, anonymizer: Anonymizer) -> None:
    """Refuse a draft the scrub would change, naming the first lines that differ."""
    clean = anonymizer.scrub(text)
    if clean == text:
        return
    changed = [number for number, (old, new)
               in enumerate(zip(text.splitlines(), clean.splitlines()), 1) if old != new]
    where = ", ".join(map(str, changed[:5])) or "the end"
    raise FeedbackError(f"the draft holds something private (line {where}); nothing was sent. "
                        "Remove it, or make a new draft.")


def title_of(text: str) -> str:
    first = text.splitlines()[0] if text.strip() else ""
    if not first.startswith("# ") or not first[2:].strip():
        raise FeedbackError("the draft must start with a `# title` line")
    return first[2:].strip()


def post_argv(repo: str, title: str, path: Path) -> list[str]:
    return ["gh", "issue", "create", "--repo", repo, "--title", title, "--body-file", str(path)]
