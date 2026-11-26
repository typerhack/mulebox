"""How a failed command tells it: the error's code, message and fix (design.md, Errors with a
code and a fix).

On stderr, two lines for people and agents alike:

    mulebox: error [node.unreachable]: pc did not answer ...
    mulebox: fix: `mulebox doctor`, then ...

With `--json`, also `{"error": {"code", "message", "fix", "exit"}}` on stdout, where the tool
reads. Messages are redacted; the exit code is the contract's, which the code only refines.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TextIO

from mulebox.common import error_codes
from mulebox.common.redact import Redactor

PREFIX = "mulebox: "


@dataclass(frozen=True)
class Failure:
    code: str
    message: str
    fix: str
    exit: int

    def as_json(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "fix": self.fix,
                          "exit": self.exit}}


def failure(exc: BaseException | str, exit_code: int, default_code: str) -> Failure:
    """What to say about `exc`: its own code and fix where it names them, else `default_code`'s."""
    code = getattr(exc, "error_code", None) or default_code
    code = code if code in error_codes.CODES else default_code
    fix = getattr(exc, "fix", None) or error_codes.fix_for(code)
    redact = Redactor().redact
    return Failure(code, redact(str(exc)), redact(fix), exit_code)


def tell(found: Failure, err: TextIO, out: TextIO | None = None) -> int:
    """Print `found` and give its exit code; `out` (the command's --json) gets the JSON too."""
    err.write(f"{PREFIX}error [{found.code}]: {found.message}\n{PREFIX}fix: {found.fix}\n")
    err.flush()
    if out is not None:
        out.write(json.dumps(found.as_json()) + "\n")
        out.flush()
    return found.exit
