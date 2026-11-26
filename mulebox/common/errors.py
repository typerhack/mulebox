"""Base exception for everything mulebox raises on purpose.

Each concern defines its own subclass in its own module (ConfigError in config.py,
ProtocolError in protocol.py, ...), so callers can catch one concern or all of them.

Every error has a stable code and a fix (design.md, Errors with a code and a fix): a class
names its code in `error_code`, and the place that raises it may name a better code or fix
(`error_code=`, `fix=`). Without either, the code table's default applies (error_codes.py).
"""

from __future__ import annotations


class MuleboxError(Exception):
    """Base class for expected, user-reportable mulebox errors."""

    error_code: str | None = None  # common/error_codes.py; None: the catcher's default
    fix: str | None = None  # a command where one exists, else what to do; None: the code's

    def __init__(self, *args: object, error_code: str | None = None,
                 fix: str | None = None) -> None:
        super().__init__(*args)
        if error_code is not None:
            self.error_code = error_code
        if fix is not None:
            self.fix = fix
