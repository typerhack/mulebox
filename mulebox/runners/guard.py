"""The guard: the first thing a runner's job-started hook does, before it holds a slot.

GitHub's runner calls the hook after it has downloaded the job's actions (files only) and
before anything of the job runs: no Docker action is built, no `container:` or `services:`
started, no step run (JobExtension.cs in actions/runner). A hook that fails does NOT stop the
job: the runner goes on and runs every later step whose `if:` holds, so a step with
`if: always()` would still run (StepsRunner.cs). So a refusal also kills the runner's job
process, `Runner.Worker`, while the hook still holds it: nothing after the hook runs, and
GitHub marks the job failed. It is the hook's first step, before the node's config is read,
and it fails closed: a runner it cannot place or metadata it cannot read refuses every job, and
a job process it cannot find to kill is held in the hook until GitHub ends it. The hook's
environment is the runner's own and GitHub's job data (the `github` context's allowlisted
names), never the workflow's `env:`, so a pull request that edits the workflow cannot change
what the guard reads. The event file at
GITHUB_EVENT_PATH is the one the runner writes from GitHub's payload.

Refused, on every runner:
- a pull request whose head repository is not its base repository (a fork), or has no id
  (a deleted fork); `pull_request`, `pull_request_target` and the review events carry it;
- a `workflow_run` whose run came from another repository;
- a comment on a pull request (`issue_comment` with `issue.pull_request`): its workflow may build
  that pull request, and the event does not say where the pull request came from;
- no event file, or one that is not a single JSON object.

On a runner registered with actors (`runner register` writes the registering account):
also a run whose actor or triggering actor (a re-run's) is not one of them. GitHub logins
are compared without case, as GitHub does.

The fork rules follow runner-up's fork guard (github.com/kunchenguid/runner-up).
"""

from __future__ import annotations

import json
import os
import signal
import time
from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import Any, TextIO

from mulebox.runners import layout
from mulebox.runners.supervise import PROC_ROOT, WORKER_NAMES, worker_pids

MAX_EVENT_BYTES = 64 * 1024 * 1024
MAX_DEPTH = 8  # parents looked at for the job's Runner.Worker


def _lookup(value: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _same_repo(head: Any, base: Any) -> bool:
    return (type(head) is int and type(base) is int and head > 0 and head == base)


def _name(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def read_event(path: str | None) -> dict[str, Any] | None:
    """The event file as one JSON object, or None when missing or anything else."""
    if not path:
        return None
    try:  # never through a symlink: an isolated runner's copy sits in a folder its job can write
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as fh:
            data = fh.read(MAX_EVENT_BYTES + 1)
    except OSError:
        return None
    if len(data) > MAX_EVENT_BYTES:
        return None
    try:
        event = json.loads(data)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def fork_reason(event: Mapping[str, Any]) -> str | None:
    """Why the event comes from another repository, or None."""
    pr = event.get("pull_request")
    if pr is not None:
        if not _same_repo(_lookup(pr, "head", "repo", "id"), _lookup(pr, "base", "repo", "id")):
            return "a pull request from " + _name(_lookup(pr, "head", "repo", "full_name"),
                                                  "a deleted fork")
    if _lookup(event, "issue", "pull_request") is not None:
        return "a run started by a comment on a pull request"
    run = event.get("workflow_run")
    if run is not None:
        if not _same_repo(_lookup(run, "head_repository", "id"),
                          _lookup(run, "repository", "id")):
            return "a follow-on run of " + _name(_lookup(run, "head_repository", "full_name"),
                                                 "a deleted fork")
    return None


def actor_reason(env: Mapping[str, str], actors: Collection[str]) -> str | None:
    """Why the run's actors are not among `actors`, or None. No actors: no check."""
    if not actors:
        return None
    allowed = {actor.lower() for actor in actors}
    seen = [env.get("GITHUB_ACTOR") or "", env.get("GITHUB_TRIGGERING_ACTOR") or ""]
    if not seen[0]:
        return "a run with no actor"
    for actor in seen:
        if actor and actor.lower() not in allowed:
            return f"a run started by {actor}"
    return None


def refusal(env: Mapping[str, str], meta: Mapping[str, Any] | None) -> str | None:
    """Why the job must not run on this runner (its `.mulebox-runner.json` as meta), or None.
    No metadata, or metadata that cannot be read, refuses every job: `runner add` has always
    written it. An `actors` entry that is not a list of names refuses every job, as does a
    runner marked `public` with no actors. A runner added before 1.3.0 has no `actors` entry
    and gets the other rules only."""
    if meta is None:
        return "every job: its .mulebox-runner.json is missing or cannot be read"
    actors = meta.get("actors", [])
    if not isinstance(actors, list) or not all(isinstance(a, str) and a for a in actors):
        return "every job: its registered accounts cannot be read"
    if meta.get("public") and not actors:
        return "every job: it serves a public repository with no registered accounts"
    event = read_event(env.get("GITHUB_EVENT_PATH"))
    if event is None:
        return "a job with no readable event file"
    return fork_reason(event) or actor_reason(env, actors)


def runner_meta(folder: Path | None) -> dict[str, Any] | None:
    """The runner's `.mulebox-runner.json`, or None when the folder is unknown or the file is
    missing or unreadable."""
    if folder is None:
        return None
    meta = layout.read_meta(folder)
    return meta or None


def _is_runner(folder: Path) -> bool:
    return (folder / ".runner").is_file() and (folder / layout.HOOKS_DIR).is_dir()


def hook_folder(env: Mapping[str, str], cwd: str | None = None) -> Path | None:
    """The runner folder this hook serves, without the node's config: from the hook path the
    runner was started with (`<folder>/mulebox-hooks/started.sh`), else the nearest folder
    above the job's working directory holding the runner's `.runner` file."""
    script = env.get(layout.HOOKS["started"])
    if script:
        folder = Path(os.path.realpath(script)).parent.parent
        if _is_runner(folder):
            return folder
    try:
        here = Path(os.path.realpath(cwd or os.getcwd()))
    except OSError:
        return None
    for folder in (here, *here.parents):
        if _is_runner(folder):
            return folder
    return None


def ancestor_workers(pid: int | None = None, proc_root: Path = PROC_ROOT) -> list[int]:
    """`Runner.Worker` processes among this process's parents: the job the hook runs in."""
    found, pid = [], pid or os.getpid()
    for _ in range(MAX_DEPTH):
        try:
            stat = (proc_root / str(pid) / "stat").read_text()
            pid = int(stat.rsplit(")", 1)[1].split()[1])
            raw = (proc_root / str(pid) / "cmdline").read_bytes()
        except (OSError, ValueError, IndexError):
            break
        if pid <= 1:
            break
        if any(Path(os.fsdecode(a)).name in WORKER_NAMES for a in raw.split(b"\0") if a):
            found.append(pid)
    return found


def _tell(pid: int, message: str, proc_root: Path = PROC_ROOT) -> None:
    """Write message to the process's stderr. The runner's listener attaches a crashed
    `Runner.Worker`'s stderr to the failed job, so GitHub can show why it was stopped, as the
    job's own log is never uploaded."""
    try:
        with open(proc_root / str(pid) / "fd" / "2", "w", encoding="utf-8") as err:
            err.write(message + "\n")
    except OSError:
        pass  # best effort: the kill matters, not the note


def kill_workers(folder: Path | None, message: str = "") -> list[int]:
    """Kill the job's runner process: the runner folder's `Runner.Worker`, and any among this
    process's parents, after writing message to its stderr. Return the ones signalled."""
    pids = set(ancestor_workers()) | set(worker_pids(folder) if folder else ())
    killed = []
    for pid in sorted(pids):
        if message:
            _tell(pid, message)
        try:
            os.kill(pid, signal.SIGKILL)
            killed.append(pid)
        except OSError:
            pass  # gone already
    return killed


def hold(poll_s: float = 2.0) -> None:
    """Keep the job in the hook while this process's parent lives: until GitHub cancels it or
    times it out. Then return, so nothing is left behind (the runner's cleanup kills only the
    hook's own process, not what it started)."""
    parent = os.getppid()
    while os.getppid() == parent:
        time.sleep(poll_s)


def admit(env: Mapping[str, str], out: TextIO, *, cwd: str | None = None,
          stop: Callable[[Path | None, str], list[int]] | None = None,
          wait: Callable[[], None] | None = None) -> bool:
    """The hook's first step. True lets the job go on. On a refusal it says why, kills the
    job's runner process and returns False. When it finds none to kill, it holds the job in
    the hook until the job's process ends, so the job cannot go on to a step of its own."""
    folder = hook_folder(env, cwd)
    reason = (refusal(env, runner_meta(folder)) if folder else
              "every job: the hook cannot tell which runner it serves")
    if not reason:
        return True
    message = (f"mulebox: this runner refuses {reason}: it runs only its own repository's "
               "jobs, started by the accounts it was registered for")
    print(message, file=out, flush=True)
    if (stop or kill_workers)(folder, message):
        print("mulebox: stopped the job's runner process, so none of its steps runs",
              file=out, flush=True)
        return False
    print("mulebox: found no runner process to stop; holding the job here until GitHub "
          "cancels it", file=out, flush=True)
    (wait or hold)()
    return False
