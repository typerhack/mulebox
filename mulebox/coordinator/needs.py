"""Can any worker run this job? The reason a queued job does not move, in words.

A job whose `needs` no worker offers would wait in the queue forever and say nothing. So:

- At submit, when workers are known and none of them offers what the job needs, the job is
  refused at once, with what to change. Offline workers count: one may come back.
- A queued job that cannot start now says why, in `waiting_for`, on every status reply. That
  covers a capable worker that went offline, and a machine with no worker connected yet.
  It stays queued: both can resolve themselves.

Being busy is not a reason: a capable online worker is simply the queue working.

A worker reports `compose-v1` and the package caches by itself (common/compose.py), so nobody
can add them to a config: a machine without them is running an older mulebox.
"""

from __future__ import annotations

from typing import Any

from mulebox.common import compose, isolation, package_cache
from mulebox.coordinator.workers import is_online

Worker = dict[str, Any]
HOW_TO_ADD = ("add it to `capabilities` in ~/.config/mulebox/node.toml on a node and "
              "restart its worker, or remove it from the project")
HOW_TO_UPGRADE = ("the node runs a mulebox too old for this project's `compose:` or "
                  "package caches; upgrade it (docs/install.md, Upgrade)")


def required(needs: list[str], env: dict[str, str]) -> list[str]:
    """What a job really needs. The client adds this for a clear message, but an older client
    does not, and an older worker would claim its job and ignore the compose files."""
    if compose.COMPOSE_FILES_KEY not in env:
        return needs
    return list(dict.fromkeys(
        (*needs, compose.DOCKER_CAPABILITY, compose.COMPOSE_CAPABILITY)))


def _missing(worker: Worker, needs: list[str]) -> list[str]:
    return sorted(set(needs) - set(worker["capabilities"]))


def capable(workers: list[Worker], needs: list[str]) -> list[Worker]:
    """The workers whose capabilities cover `needs`, online or not, in the given order.

    This is the same test `queue.claim` makes, so a queued job can only ever start on one
    of these; the dashboard shows them as where the job may go (never as an assignment).
    """
    return [w for w in workers if not _missing(w, needs)]


def _offers(worker: Worker) -> str:
    return ", ".join(worker["capabilities"]) or "nothing"


def _nobody_offers(needs: list[str], workers: list[Worker]) -> str:
    known = "; ".join(f"{w['worker']} offers {_offers(w)}" for w in workers)
    return f"no node offers {', '.join(sorted(set(needs)))} ({known})"


HOW_TO_ISOLATE = ("every node runs its jobs isolated (`isolation = \"container\"` in its "
                  "node.toml), and a project cannot go below that: remove `isolation: none` "
                  "from .mulebox.yml; a node older than mulebox 1.20 is upgraded "
                  "(docs/install.md, Upgrade)")


def _what_to_do(workers: list[Worker], needs: list[str]) -> str:
    if isolation.UNISOLATED in needs and all(
            isolation.UNISOLATED in _missing(w, needs) for w in workers):
        return HOW_TO_ISOLATE
    return HOW_TO_UPGRADE if any(_too_old(w, needs) for w in workers) else HOW_TO_ADD


def _too_old(worker: Worker, needs: list[str]) -> bool:
    """It lacks something every current worker reports by itself."""
    missing = _missing(worker, needs)
    return bool(set(missing) & set(package_cache.CAPABILITIES)) or (
        compose.COMPOSE_CAPABILITY in missing
        and compose.DOCKER_CAPABILITY in worker["capabilities"])


def refusal(workers: list[Worker], needs: list[str]) -> str | None:
    """Why a job with `needs` must not be queued at all, or None."""
    if not workers or any(not _missing(w, needs) for w in workers):
        return None
    return f"{_nobody_offers(needs, workers)}: {_what_to_do(workers, needs)}"


def waiting_for(workers: list[Worker], needs: list[str], now: float) -> str | None:
    """Why a queued job cannot start right now, or None when a worker for it is online."""
    if not workers:
        return "no node has connected to this coordinator yet"
    fitting = capable(workers, needs)
    if not fitting:
        return f"{_nobody_offers(needs, workers)}: {_what_to_do(workers, needs)}"
    online = [w for w in fitting if is_online(w, now)]
    if any(not w.get("draining") for w in online):
        return None
    if online:
        names = ", ".join(w["worker"] for w in online)
        return (f"every node for this job is draining ({names}); "
                f"`mulebox machine resume <name>` lets one take it")
    names = ", ".join(w["worker"] for w in fitting)
    return f"no node for this job is online (offline: {names})"


def fleet_for(workers: list[Worker], job: dict[str, Any]) -> list[Worker]:
    """The workers a job may go to: with `--on` (`pinned_worker`), that one only."""
    pinned = job.get("pinned_worker") if job.get("kind", "job") == "job" else None
    return [w for w in workers if w["worker"] == pinned] if pinned else workers


def on_refusal(workers: list[Worker], name: str, needs: list[str]) -> str | None:
    """Why a job sent `--on <name>` must not be queued, or None: a node nobody knows, or one
    that does not offer what the job needs."""
    named = [w for w in workers if w["worker"] == name]
    if not named:
        known = ", ".join(sorted(w["worker"] for w in workers)) or "none yet"
        return (f"no node is named {name} (nodes: {known}); `mulebox machine list` shows "
                "their names")
    return refusal(named, needs)
