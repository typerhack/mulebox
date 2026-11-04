"""Can any worker run this job? The reason a queued job does not move, in words.

A job whose `needs` no worker offers would wait in the queue forever and say nothing. So:

- At submit, when workers are known and none of them offers what the job needs, the job is
  refused at once, with what to change. Offline workers count: one may come back.
- A queued job that cannot start now says why, in `waiting_for`, on every status reply. That
  covers a capable worker that went offline, and a machine with no worker connected yet.
  It stays queued: both can resolve themselves.

Being busy is not a reason: a capable online worker is simply the queue working.
"""

from __future__ import annotations

from typing import Any

from mulebox.coordinator.workers import is_online

Worker = dict[str, Any]
HOW_TO_ADD = ("add it to `capabilities` in ~/.config/mulebox/node.toml on a build machine and "
              "restart its worker, or remove it from the project")


def _missing(worker: Worker, needs: list[str]) -> list[str]:
    return sorted(set(needs) - set(worker["capabilities"]))


def _offers(worker: Worker) -> str:
    return ", ".join(worker["capabilities"]) or "nothing"


def _nobody_offers(needs: list[str], workers: list[Worker]) -> str:
    known = "; ".join(f"{w['worker']} offers {_offers(w)}" for w in workers)
    return f"no build machine offers {', '.join(sorted(set(needs)))} ({known})"


def refusal(workers: list[Worker], needs: list[str]) -> str | None:
    """Why a job with `needs` must not be queued at all, or None."""
    if not workers or any(not _missing(w, needs) for w in workers):
        return None
    return f"{_nobody_offers(needs, workers)}: {HOW_TO_ADD}"


def waiting_for(workers: list[Worker], needs: list[str], now: float) -> str | None:
    """Why a queued job cannot start right now, or None when a worker for it is online."""
    if not workers:
        return "no build machine has connected to this coordinator yet"
    capable = [w for w in workers if not _missing(w, needs)]
    if not capable:
        return _nobody_offers(needs, workers)
    if any(is_online(w, now) for w in capable):
        return None
    names = ", ".join(w["worker"] for w in capable)
    return f"no build machine for this job is online (offline: {names})"
