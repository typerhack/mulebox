"""`--json` on the commands that print as they go (check, run, wait, cancel, ok, fetch, hold,
logs). Their usual output, the log included, goes to stderr; stdout gets one JSON object at the
end, `{"exit", "notices", ...}`: the command's exit code, the notices it gave (attention.py: kind, text and the coordinator's
data), and
what the command recorded here, such as a job's result. An error gives `{"error": ...}` instead,
as on every --json command (common/error_report.py).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Callable, Iterator
from typing import Any, TextIO

_ended: dict[str, Any] = {}
_notices: list[dict[str, Any]] | None = None


def add(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true",
                        help="output on stderr, one JSON object on stdout at the end")
    parser.set_defaults(json_end=True)


def wanted(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json_end", False) and getattr(args, "json", False))


def record(**facts: Any) -> None:
    """What the end object says besides `exit` and `notices`; a no-op outside --json."""
    if _notices is not None:
        _ended.update({k: v for k, v in facts.items() if v is not None})


def noticed(item: dict[str, Any]) -> None:
    if _notices is not None:
        _notices.append(item)


@contextlib.contextmanager
def collecting(out: TextIO | None = None) -> Iterator[Callable[[int], None]]:
    """Print to stderr inside; the callable yielded writes the end object to `out`."""
    global _notices
    real = out or sys.stdout
    _ended.clear()
    _notices = said = []

    def end(code: int) -> None:  # called once stdout is back, after the with block
        real.write(json.dumps({**_ended, "exit": code, "notices": said}, sort_keys=True) + "\n")
        real.flush()

    try:
        with contextlib.redirect_stdout(sys.stderr):
            yield end
    finally:
        _notices = None
