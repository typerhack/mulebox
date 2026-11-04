"""Blocking work beside the worker's loop, so the loop keeps its heartbeats going.

The loop may not stop: other jobs need heartbeats within their lease, a cancel has to get
through, and runner reservations are watched. Docker calls can take a minute each when the
daemon is stuck, so what is made of them runs here. A task never raises into the loop: it
ends with `done` true, and `error` says what stopped it.
"""

from __future__ import annotations

import threading
from collections.abc import Callable


class Task:
    def __init__(self, work: Callable[[], None]) -> None:
        self._work = work
        self._finished = threading.Event()
        self.error: Exception | None = None

    def run(self) -> None:
        try:
            self._work()
        except Exception as exc:  # reported through `error`; a thread has nowhere else to go
            self.error = exc
        finally:
            self._finished.set()

    @property
    def done(self) -> bool:
        return self._finished.is_set()

    def wait(self, timeout_s: float) -> bool:
        return self._finished.wait(timeout_s)


def start_thread(work: Callable[[], None]) -> Task:
    """A daemon thread: a worker told to stop must not hang on a stuck daemon. Whatever a
    killed task leaves is found by label on the next start (cleaner.py)."""
    task = Task(work)
    threading.Thread(target=task.run, name="mulebox-cleanup", daemon=True).start()
    return task
