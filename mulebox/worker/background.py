"""Blocking work beside the worker's loop, so the loop keeps its heartbeats going.

The loop may not stop: other jobs need heartbeats within their lease, a cancel has to get
through, and runner reservations are watched. Docker calls can take a minute each when the
daemon is stuck, so what is made of them runs here. A task never raises into the loop: it
ends with `done` true, and `error` says what stopped it.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


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


class Polled(Generic[T]):
    """An answer asked for beside the loop: a stuck daemon must not stop it. `value()` gives the
    last answer and asks again; None until there is one, while the next one is late, or when
    asking failed."""

    def __init__(self, ask: Callable[[], T]) -> None:
        self._ask = ask
        self._task: Task | None = None
        self._found: T | None = None

    def _run(self) -> None:
        self._found = None
        self._found = self._ask()

    def value(self) -> T | None:
        task = self._task
        if task is not None and not task.done:
            return None
        found = self._found if task is not None else None
        self._task = start_thread(self._run)
        return found


def start_thread(work: Callable[[], None]) -> Task:
    """A daemon thread: a worker told to stop must not hang on a stuck daemon. Whatever a
    killed task leaves is found by label on the next start (cleaner.py)."""
    task = Task(work)
    threading.Thread(target=task.run, name="mulebox-cleanup", daemon=True).start()
    return task
