"""The dev machine side of runner management: get a token with `gh`, run `mulebox runner` there.

`register` asks GitHub for a registration token
(`gh api -X POST repos/<owner/repo>/actions/runners/registration-token --jq .token`) and
runs `mulebox runner add --repo <owner/repo> ...` on the coordinator over `common.ssh`,
with the token on stdin. `unregister` does the same with `remove-token` and
`mulebox runner remove --repo <owner/repo>`. The token is never in an argv (neither of
ssh nor of the remote command); remote output and every error are redacted with it.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from typing import TextIO

from mulebox.client.remote import remote_program
from mulebox.common import ssh
from mulebox.common.config import ClientConfig
from mulebox.common.errors import MuleboxError
from mulebox.common.redact import Redactor
from mulebox.runners.names import check_name, check_repo, parse_labels

GH_TIMEOUT_S = 60
KINDS = {"registration": "registration-token", "remove": "remove-token"}

GhRun = Callable[[Sequence[str]], subprocess.CompletedProcess]
Stream = Callable[..., Iterator[bytes]]


class GitHubError(MuleboxError):
    """`gh` could not produce a token, or the node refused the runner command."""


def run_gh(argv: Sequence[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(list(argv), capture_output=True, text=True,
                              timeout=GH_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise GitHubError(f"`gh api` did not answer within {GH_TIMEOUT_S} s") from None
    except OSError as exc:
        raise GitHubError(f"cannot run the GitHub CLI `gh` ({exc.strerror}); install it "
                          "and run `gh auth login`") from None


def gh_argv(repo: str, kind: str) -> list[str]:
    return ["gh", "api", "-X", "POST",
            f"repos/{check_repo(repo)}/actions/runners/{KINDS[kind]}", "--jq", ".token"]


def gh_token(repo: str, kind: str, run: GhRun = run_gh) -> str:
    """A short-lived runner token from GitHub (kind: registration or remove)."""
    proc = run(gh_argv(repo, kind))
    token = (proc.stdout or "").strip()
    if proc.returncode != 0 or not token or any(c.isspace() for c in token):
        detail = Redactor([token] if token else []).redact((proc.stderr or "").strip())
        raise GitHubError(
            f"gh could not get a {kind} token for {repo}: {detail[-500:] or 'no output'}. "
            "It needs `gh auth login` with admin rights on the repository.")
    return token


def refuse_public(repo: str, run: GhRun = run_gh) -> None:
    """Refuse a public repository: a fork's pull request brings its own workflow file, so it
    could name this runner and run its code on the node (docs/install.md). A
    visibility `gh` cannot read is left to the token request, which fails with the reason."""
    proc = run(["gh", "api", f"repos/{check_repo(repo)}", "--jq", ".visibility"])
    if proc.returncode == 0 and (proc.stdout or "").strip() == "public":
        raise GitHubError(
            f"{repo} is public, and a runner there would run any fork's pull request on the "
            "node; mulebox attaches runners to private repositories only")


def remote_argv(config: ClientConfig, action: str, repo: str, name: str | None,
                labels: str | None = None) -> list[str]:
    argv = [remote_program(config.remote_bin), "runner", action, "--repo", check_repo(repo)]
    if name is not None:
        argv += ["--name", check_name(name)]
    if labels is not None:
        argv += ["--labels", ",".join(parse_labels(labels))]
    return argv


def _run_remote(config: ClientConfig, argv: list[str], token: str, out: TextIO,
                stream: Stream) -> None:
    redactor = Redactor([token])
    try:
        for line in stream(config.coordinator, argv, stdin=(token + "\n").encode(),
                           connect_timeout_s=config.connect_timeout_s):
            out.write(redactor.redact(line.decode("utf-8", errors="replace")))
            out.flush()
    except ssh.RemoteError as exc:
        raise GitHubError(redactor.redact(str(exc))) from None
    except ssh.SSHError as exc:
        raise type(exc)(redactor.redact(str(exc))) from None


def register(config: ClientConfig, repo: str, *, name: str | None = None,
             labels: str | None = None, run: GhRun = run_gh,
             stream: Stream = ssh.stream_remote, out: TextIO = sys.stdout) -> None:
    argv = remote_argv(config, "add", repo, name, labels)
    refuse_public(repo, run)
    _run_remote(config, argv, gh_token(repo, "registration", run), out, stream)


def unregister(config: ClientConfig, repo: str, *, name: str | None = None,
               run: GhRun = run_gh, stream: Stream = ssh.stream_remote,
               out: TextIO = sys.stdout) -> None:
    argv = remote_argv(config, "remove", repo, name)
    _run_remote(config, argv, gh_token(repo, "remove", run), out, stream)
