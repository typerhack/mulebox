"""CLI `mulebox feedback draft|post`. Drafting is local; only `post` sends anything."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from mulebox.client import feedback, report
from mulebox.client.commands import Handler, UsageError, guarded
from mulebox.client.remote import Remote, request
from mulebox.common.anonymize import Anonymizer
from mulebox.common.config import (
    ClientConfig,
    ConfigError,
    ProjectConfig,
    find_project_config,
    load_client_config,
    load_project_config,
)
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import MessageType
from mulebox.common.ssh import SSHError
from mulebox.runners.github import GitHubError, run_gh
from mulebox.version import get_version

QUEUE_LIMIT = 200


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("feedback", help="report what mulebox could not handle")
    actions = parser.add_subparsers(dest="feedback_command", metavar="<action>", required=True)
    made = actions.add_parser("draft", help="print a scrubbed issue draft; sends nothing")
    made.add_argument("job_id", nargs="?", help="the job this is about")
    made.add_argument("--summary", required=True, help="what happened, in plain words")
    made.add_argument("--log", action="store_true", help="include the job's last log lines")
    made.set_defaults(func=_guarded(_draft))
    sent = actions.add_parser("post", help="open a GitHub issue from a reviewed draft file")
    sent.add_argument("file", type=Path)
    sent.set_defaults(func=_guarded(_post))


def _guarded(handler: Handler) -> Handler:
    def run(args: argparse.Namespace) -> int:
        try:
            return guarded(handler)(args)
        except (feedback.FeedbackError, GitHubError) as exc:
            report.status(sys.stderr, f"error: {exc}")
            return report.EXIT_USAGE
    return run


def _context() -> tuple[ProjectConfig | None, Path | None, ClientConfig | None]:
    """All optional: a report about a broken setup must still be possible."""
    project, root, config = None, None, None
    try:
        path = find_project_config(Path.cwd())
        root = path.parent
        project = load_project_config(path)
    except ConfigError:
        pass
    try:
        config = load_client_config()
    except ConfigError:
        pass
    return project, root, config


def _queue(remote: Remote) -> list[dict[str, Any]]:
    reply = remote.call(request(MessageType.QUEUE, limit=QUEUE_LIMIT))
    jobs = reply.body.get("jobs")
    return [j for j in jobs if isinstance(j, dict)] if isinstance(jobs, list) else []


def _queue_or_nothing(config: ClientConfig | None) -> list[dict[str, Any]]:
    """Names from the coordinator make a scrub better; being offline must not stop it."""
    if config is None:
        return []
    try:
        return _queue(Remote(config))
    except (MuleboxError, SSHError, OSError):
        return []


def _read_log(remote: Remote, job_id: str) -> str:
    text, offset = "", 0
    while True:
        body = remote.call(request(MessageType.LOGS, job_id=job_id, offset=offset)).body
        text += body.get("data", "")
        following = body.get("next_offset", offset)
        if body.get("eof", True) or following == offset:
            return text
        offset = following


def _draft(args: argparse.Namespace) -> int:
    if not args.summary.strip():
        raise UsageError("--summary needs some text")
    if args.log and not args.job_id:
        raise UsageError("--log needs a job id")
    project, root, config = _context()
    jobs = _queue_or_nothing(config)
    names = feedback.local_names(project, root, config) | feedback.names_in(jobs)
    job, log = None, None
    if args.job_id:
        if config is None:
            raise UsageError("a job id needs the client config, to reach the coordinator")
        remote = Remote(config)
        job = dict(remote.call(request(MessageType.STATUS, job_id=args.job_id)).body)
        if args.log:
            log = _read_log(remote, args.job_id)
    text = feedback.draft(args.summary, get_version(), Anonymizer(names), job, log)
    sys.stdout.write(text)
    return 0


def _post(args: argparse.Namespace) -> int:
    project, root, config = _context()
    if config is None or not config.feedback_repo:
        raise UsageError("set feedback_repo = \"owner/name\" in client.toml first")
    try:
        text = args.file.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"cannot read {args.file}: {exc.strerror}") from None
    title = feedback.title_of(text)
    names = feedback.local_names(project, root, config) | feedback.names_in(
        _queue_or_nothing(config))
    feedback.check_clean(text, Anonymizer(names))
    done = run_gh(feedback.post_argv(config.feedback_repo, title, args.file))
    if done.returncode != 0:
        raise GitHubError(f"gh could not open the issue: {done.stderr.strip()[-300:]}")
    print(done.stdout.strip())
    return 0
