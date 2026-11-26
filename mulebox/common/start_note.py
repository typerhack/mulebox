"""The worker's last word in the log of a job that could not start: what failed, its code and
what to do (design.md, Errors with a code and a fix). The client's summary keeps both lines.

    mulebox: the job could not start: [toolchain.failed] node 99.0.0 does not exist ...
    mulebox: fix: pin a version the node has ...
"""

from __future__ import annotations

from mulebox.common import error_codes
from mulebox.common.status import FIX_NOTE, NOT_STARTED_NOTE

DEFAULT = "start.failed"  # an error of no code of its own (an OSError, say)


def lines(problem: BaseException | str, code: str | None = None) -> str:
    """The two lines for `problem`: its own code and fix where it names them, else `code`'s."""
    code = code or getattr(problem, "error_code", None) or DEFAULT
    code = code if code in error_codes.CODES else DEFAULT
    fix = getattr(problem, "fix", None) or error_codes.fix_for(code)
    return f"{NOT_STARTED_NOTE} [{code}] {problem}\n{FIX_NOTE} {fix}\n"
