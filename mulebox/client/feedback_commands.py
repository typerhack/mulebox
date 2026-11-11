"""CLI `mulebox feedback draft|post`. Drafting is local; only `post` sends anything."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from mulebox.client import feedback, feedback_guide, report
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
    made = actions.add_parser(
        "draft", help="print a scrubbed issue draft (or write it with -o); sends nothing",
        description="Builds a scrubbed issue draft and prints it, or writes it to -o FILE for "
                    "`mulebox feedback post FILE`. Nothing is sent. See `mulebox feedback guide`.")
    made.add_argument("job_ids", nargs="*", metavar="job_id", help="the jobs this is about")
    made.add_argument("--summary", required=True, help="what happened, in plain words")
    made.add_argument("--title", help="the issue title (default: the summary's first sentence)")
    made.add_argument("--log", action="store_true", help="include each job's last log lines")
    made.add_argument("--log-lines", type=int, default=feedback.LOG_LINES, metavar="N",
                      help=f"how many last lines --log takes (default {feedback.LOG_LINES})")
    made.add_argument("--grep", metavar="PATTERN",
                      help="include each job's log lines matching PATTERN, with the lines around")
    made.add_argument("-o", "--output", type=Path, metavar="FILE", help="write the draft here")
    made.set_defaults(func=_guarded(_draft))
    told = actions.add_parser("guide", help="how to report a problem with mulebox")
    told.set_defaults(func=_guarded(_guide))
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


def _pick_lines(remote: Remote, job_id: str, args: argparse.Namespace) -> str:
    log = _read_log(remote, job_id)
    parts = [feedback.matching(log, args.grep)] if args.grep else []
    if args.log:
        parts.append(feedback.tail(log, max(1, args.log_lines)))
    return "\n...\n".join(part for part in parts if part)


def _draft(args: argparse.Namespace) -> int:
    if not args.summary.strip():
        raise UsageError("--summary needs some text")
    if (args.log or args.grep) and not args.job_ids:
        raise UsageError("--log and --grep need a job id")
    project, root, config = _context()
    jobs = _queue_or_nothing(config)
    names = feedback.local_names(project, root, config) | feedback.names_in(jobs)
    found, logs = [], {}
    if args.job_ids:
        if config is None:
            raise UsageError("a job id needs the client config, to reach the coordinator")
        remote = Remote(config)
        for job_id in dict.fromkeys(args.job_ids):
            body = dict(remote.call(request(MessageType.STATUS, job_id=job_id)).body)
            names |= feedback.names_in([body])
            found.append(body)
            if args.log or args.grep:
                logs[job_id] = _pick_lines(remote, job_id, args)
    text = feedback.draft(args.summary, get_version(), Anonymizer(names), found, logs, args.title)
    if args.output is None:
        sys.stdout.write(text)
        return 0
    try:
        args.output.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"cannot write {args.output}: {exc.strerror}") from None
    report.status(sys.stderr, f"draft written to {args.output}; read it, then "
                              f"`mulebox feedback post {args.output}`")
    return 0


def _guide(args: argparse.Namespace) -> int:
    sys.stdout.write(feedback_guide.TEXT)
    return 0


def _post(args: argparse.Namespace) -> int:
    project, root, config = _context()
    if config is None or not config.feedback_repo:
        raise UsageError("set feedback_repo = \"owner/name\" in client.toml first")
    if project is not None and project.project in config.feedback_off:
        raise UsageError(f"feedback is off for {project.project} (feedback_off in client.toml): its "
                         "problems are not posted; tell the user instead")
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
