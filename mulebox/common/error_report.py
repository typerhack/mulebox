"""How a failed command tells it: the error's code, message and fix (design.md, Errors with a
code and a fix). Every mulebox command, on a dev machine or a node, prints its errors here.

On stderr, two lines for people and agents alike:

    mulebox: error [node.unreachable]: pc did not answer ...
    mulebox: fix: `mulebox doctor`, then ...

With `--json`, also `{"error": {"code", "message", "fix", "exit"}}` on stdout, where the tool
reads. Messages are redacted; the exit code is the command's, which the code only refines.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, TextIO

from mulebox.common import error_codes
from mulebox.common.errors import MuleboxError
from mulebox.common.redact import Redactor

PREFIX = "mulebox: "
# (error types, exit code, default code): the first that matches an error tells it.
Kinds = tuple[tuple[tuple[type[BaseException], ...], int, str], ...]


@dataclass(frozen=True)
class Failure:
    code: str
    message: str
    fix: str
    exit: int

    def as_json(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "fix": self.fix,
                          "exit": self.exit}}


def failure(exc: BaseException | str, exit_code: int, default_code: str,
            secrets: Iterable[str] = ()) -> Failure:
    """What to say about `exc`: its own code and fix where it names them, else `default_code`'s."""
    code = getattr(exc, "error_code", None) or default_code
    code = code if code in error_codes.CODES else default_code
    fix = getattr(exc, "fix", None) or error_codes.fix_for(code)
    redact = Redactor(list(secrets)).redact
    return Failure(code, redact(str(exc)), redact(fix), exit_code)


def tell(found: Failure, err: TextIO, out: TextIO | None = None) -> int:
    """Print `found` and give its exit code; `out` (the command's --json) gets the JSON too."""
    err.write(f"{PREFIX}error [{found.code}]: {found.message}\n{PREFIX}fix: {found.fix}\n")
    err.flush()
    if out is not None:
        out.write(json.dumps(found.as_json()) + "\n")
        out.flush()
    return found.exit


def report(exc: BaseException, kinds: Kinds = (), *, exit_code: int | None = None,
           default_code: str | None = None, as_json: bool = False,
           secrets: Iterable[str] = ()) -> int:
    """Tell `exc` on stderr (and stdout with `as_json`) and give the exit code. The first of
    `kinds` that matches gives the exit and default code unless given; an error of no kind is
    `mulebox.internal`, exit 1, with its trace when MULEBOX_DEBUG is set."""
    for types, kind_exit, kind_code in kinds:
        if isinstance(exc, types):
            exit_code, default_code = exit_code or kind_exit, default_code or kind_code
            break
    else:
        if not isinstance(exc, MuleboxError):
            if os.environ.get("MULEBOX_DEBUG"):
                traceback.print_exception(exc, file=sys.stderr)
            exc = MuleboxError(f"{type(exc).__name__}: {exc}", error_code="mulebox.internal")
        exit_code, default_code = exit_code or 1, default_code or "mulebox.internal"
    found = failure(exc, exit_code, default_code, secrets)
    return tell(found, sys.stderr, sys.stdout if as_json else None)
