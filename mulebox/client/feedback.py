"""Issue drafts about what mulebox could not handle (docs/design.md, Agent feedback).

`draft` builds markdown and prints it or writes it to a file; nothing leaves the machine. `post`
sends a file only if it passes the scrub again unchanged, so what was reviewed is what is sent
and nothing private can be added on the way; a refusal names the line and the kind of thing.
A draft holds the summary, the mulebox version, the operating system and, per job id given, the
id, its result, stages and the mulebox that ran it, so the owner can trace it. Never a project,
branch or machine name; log lines only when asked for, and scrubbed like everything else.
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
from mulebox.common.anonymize import PLACEHOLDER, Anonymizer
from mulebox.common.config import ClientConfig, ProjectConfig
from mulebox.common.errors import MuleboxError

TITLE_CHARS = 240  # GitHub takes 256; a title is cut only when it would be refused
LOG_LINES = 40
LOG_CHARS = 8000
CONTEXT_LINES = 2  # around each line `--grep` picks
NAME_FIELDS = ("project", "branch", "client", "worker")
JOB_FIELDS = ("job", "kind", "state", "outcome", "exit_code", "duration_s", "stage",
              "stop_reason", "worker_version")
_REPO_IN_URL = re.compile(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z`(\[])")


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


def tail(log: str, lines: int = LOG_LINES) -> str:
    """The last `lines` lines, each with its line number in the log (as `mulebox logs` counts)."""
    rows = log.splitlines()
    first = max(0, len(rows) - lines)
    return "\n".join(f"{n}: {row}" for n, row in enumerate(rows[first:], first + 1))[-LOG_CHARS:]


def matching(log: str, pattern: str) -> str:
    """Lines matching `pattern` (a regular expression) with CONTEXT_LINES around each, numbered,
    gaps marked: the failure is often far from the end, as in a CI log that ends in git cleanup."""
    rows = log.splitlines()
    try:
        wanted = re.compile(pattern)
    except re.error as exc:
        raise FeedbackError(f"--grep is not a valid pattern: {exc}") from None
    keep = sorted({k for n, row in enumerate(rows) if wanted.search(row)
                   for k in range(max(0, n - CONTEXT_LINES), min(len(rows), n + CONTEXT_LINES + 1))})
    out, last = [], None
    for n in keep:
        if last is not None and n != last + 1:
            out.append("...")
        out.append(f"{n + 1}: {rows[n]}")
        last = n
    return "\n".join(out)[-LOG_CHARS:]


def title_from(summary: str, title: str | None = None) -> str:
    """`title` if given, else the first sentence of the summary's first line; cut only when too
    long for GitHub, and then at a word."""
    line = (title or "").strip() or _SENTENCE_END.split(summary.strip().splitlines()[0])[0]
    if len(line) <= TITLE_CHARS:
        return line
    return line[:TITLE_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:") or line[:TITLE_CHARS]


def _job_section(job: dict[str, Any]) -> list[str]:
    lines = ["", f"### {job.get('job_id', 'job')}", ""]
    lines += [f"- {name}: {job.get(name)}" for name in JOB_FIELDS if job.get(name) not in (None, "")]
    ci = job.get("ci_result") or {}
    if ci.get("step"):
        said = f": {ci['message']}" if ci.get("message") else ""
        lines.append(f"- GitHub step that failed: {ci['step']}{said}")
    steps = [row for row in job.get("steps") or [] if isinstance(row, dict)]
    if steps:
        lines += ["", "| stage | seconds | exit | failing line |", "|---|---|---|---|"]
        for row in steps:
            took = (round(row["finished_at"] - row["started_at"], 1)
                    if isinstance(row.get("finished_at"), (int, float))
                    and isinstance(row.get("started_at"), (int, float)) else "open")
            failing = str(row.get("failing_line") or "").replace("|", "/")
            lines.append(f"| {row.get('stage')} | {took} | {row.get('exit_code', '')} | {failing} |")
    return lines


def draft(summary: str, version: str, anonymizer: Anonymizer,
          jobs: list[dict[str, Any]] | None = None, logs: dict[str, str] | None = None,
          title: str | None = None) -> str:
    """The issue as markdown, scrubbed. `logs` maps a job id to the log lines already picked."""
    lines = [f"# {title_from(summary, title)}", "", "## What happened", "", summary.strip(), "",
             "## Environment", "", f"- mulebox {version} (this client)",
             f"- laptop: {platform.system()}, Python {platform.python_version()}"]
    if jobs:
        lines += ["", "## Jobs"]
        for job in jobs:
            lines += _job_section(job)
    for job_id, text in (logs or {}).items():
        if text:
            lines += ["", f"## Log lines of {job_id} (line numbers as in `mulebox logs`)", "",
                      "```", text, "```"]
    lines += ["", "Names of the project, people and machines, and private links and addresses, "
              f"are replaced by placeholders such as {PLACEHOLDER}, also inside longer words."]
    return anonymizer.scrub("\n".join(lines)) + "\n"


def check_clean(text: str, anonymizer: Anonymizer) -> None:
    """Refuse a draft the scrub would change, saying on which lines and what kind of thing."""
    if anonymizer.scrub(text) == text:
        return
    found = anonymizer.findings(text) or [(0, "something at the end")]
    where = "; ".join(f"line {number}: {kind}" for number, kind in found[:8])
    raise FeedbackError(f"the draft holds something private ({where}); nothing was sent. "
                        "Replace each with a placeholder or a plain description, or make a new "
                        "draft with `mulebox feedback draft`, which scrubs for you.")


def title_of(text: str) -> str:
    first = text.splitlines()[0] if text.strip() else ""
    if not first.startswith("# ") or not first[2:].strip():
        raise FeedbackError("the draft must start with a `# title` line")
    return first[2:].strip()


def post_argv(repo: str, title: str, path: Path) -> list[str]:
    return ["gh", "issue", "create", "--repo", repo, "--title", title, "--body-file", str(path)]
