"""Errors the coordinator turns into `error` replies (docs/interfaces-m1.md, Wire usage).

Each class carries the wire `code`. Anything else raised while handling a request becomes
code `internal`.
"""

from mulebox.common.errors import MuleboxError


class CoordinatorError(MuleboxError):
    """Base class; `code` is the machine-readable word sent in the error reply."""

    code = "internal"
    error_code = "node.internal"  # common/error_codes.py; a raise may name a closer one


class NotFound(CoordinatorError):
    code = "not_found"
    error_code = "request.not_found"


class BadRequest(CoordinatorError):
    code = "bad_request"
    error_code = "request.invalid"


class Conflict(CoordinatorError):
    """The request does not fit the job's current state or attempt."""

    code = "conflict"
    error_code = "request.conflict"


class NoWorker(CoordinatorError):
    """No known worker offers what the job needs, so it would wait forever."""

    code = "no_worker"
    error_code = "job.no_node"


class TooLarge(CoordinatorError):
    code = "too_large"
    error_code = "request.too_large"
