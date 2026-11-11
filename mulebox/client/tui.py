"""`mulebox queue --watch`: full-screen live view of the queue (M1.7).

Redraws every 2 s with plain ANSI escapes on the alternate screen; `q` or Ctrl-C quits.
The terminal (cursor, screen, line mode) is restored on every exit, also on errors. A
failed refresh (node unreachable) shows in the footer and is retried. When
stdout is not a terminal the table is printed once instead.
"""

from __future__ import annotations

import os
import select
import shutil
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TextIO

from mulebox.client.queue_view import render_screen, render_table

REFRESH_S = 2.0
ENTER = "\x1b[?1049h\x1b[?25l"  # alternate screen, hide cursor
LEAVE = "\x1b[?25h\x1b[?1049l"  # show cursor, main screen
HOME_CLEAR = "\x1b[H\x1b[2J"

Fetch = Callable[[], list[dict[str, Any]]]


def show_once(fetch: Fetch, out: TextIO, now: float | None = None) -> None:
    """Plain table, printed once (non-TTY or `mulebox queue`)."""
    width = shutil.get_terminal_size((200, 24)).columns if out.isatty() else 10_000
    lines = render_table(fetch(), time.time() if now is None else now, width, full_ids=True)
    out.write("\n".join(lines) + "\n")
    out.flush()


def frame(jobs: list[dict[str, Any]], now: float, size: tuple[int, int], target: str,
          error: str | None) -> str:
    """The full escape sequence for one redraw (pure)."""
    width, height = size
    stamp = time.strftime("%H:%M:%S", time.localtime(now))
    header = f"mulebox queue on {target}   {stamp}"
    footer = f"error: {error}   (retrying)" if error else "q quits, refresh every 2 s"
    lines = render_screen(jobs, now, width, height, header, footer)
    return HOME_CLEAR + "\r\n".join(lines)


def live(
    fetch: Fetch,
    target: str,
    out: TextIO,
    keys: Callable[[float], str],
    size: Callable[[], tuple[int, int]],
    clock: Callable[[], float] = time.time,
) -> None:
    """Redraw until `keys(timeout)` returns `q`. Errors from `fetch` show in the footer."""
    jobs: list[dict[str, Any]] = []
    while True:
        error = None
        try:
            jobs = fetch()
        except Exception as exc:  # shown on screen; the loop keeps trying
            error = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        out.write(frame(jobs, clock(), size(), target, error))
        out.flush()
        if "q" in keys(REFRESH_S).lower():
            return


def watch(fetch: Fetch, target: str, out: TextIO | None = None) -> int:
    """Entry point for `mulebox queue --watch`."""
    out = out or sys.stdout
    stdin = sys.stdin
    if not (out.isatty() and stdin.isatty()):
        show_once(fetch, out)
        return 0
    with _terminal(stdin.fileno(), out):
        try:
            live(fetch, target, out, lambda t: _read_keys(stdin.fileno(), t), _size)
        except KeyboardInterrupt:
            pass
    return 0


def _size() -> tuple[int, int]:
    size = shutil.get_terminal_size((80, 24))
    return size.columns, size.lines


def _read_keys(fd: int, timeout: float) -> str:
    ready, _, _ = select.select([fd], [], [], timeout)
    if not ready:
        return ""
    return os.read(fd, 64).decode("utf-8", errors="replace")


@contextmanager
def _terminal(fd: int, out: TextIO) -> Iterator[None]:
    """Character mode without echo plus the alternate screen; always restored."""
    import termios
    import tty

    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        out.write(ENTER)
        out.flush()
        yield
    finally:
        out.write(LEAVE)
        out.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
