"""Errors the coordinator turns into `error` replies (docs/interfaces-m1.md, Wire usage).

Each class carries the wire `code`. Anything else raised while handling a request becomes
code `internal`.
"""

from mulebox.common.errors import MuleboxError


class CoordinatorError(MuleboxError):
    """Base class; `code` is the machine-readable word sent in the error reply."""

    code = "internal"


class NotFound(CoordinatorError):
    code = "not_found"


class BadRequest(CoordinatorError):
    code = "bad_request"


class Conflict(CoordinatorError):
    """The request does not fit the job's current state or attempt."""

    code = "conflict"


class TooLarge(CoordinatorError):
    code = "too_large"
