"""What a failed download looks like in a log, for the worker and for the failure summary.

The usual Go errors, from Docker, and the codes npm, pnpm and Node print. A connection refused is
not in the shared list: in a job's own tests that is usually its own service not being up.
"""

from __future__ import annotations

import re

_LOST = (r"no such host", r"connection reset", r"i/o timeout", r"TLS handshake timeout",
         r"context deadline exceeded", r"name resolution", r"server misbehaving",
         r"network is unreachable", r"no route to host", r"\bETIMEDOUT\b", r"\bECONNRESET\b",
         r"\bENOTFOUND\b", r"\bEAI_AGAIN\b", r"\bENETUNREACH\b", r"ERR_SOCKET_TIMEOUT")
_REGISTRY = (r"dial tcp", r"connection refused", r"unexpected EOF", r"toomanyrequests",
             r"\b50[234]\b.*(Bad Gateway|Service Unavailable|Gateway Time)")

LOST = re.compile("|".join(_LOST), re.IGNORECASE)
REGISTRY = re.compile("|".join((*_LOST, *_REGISTRY)), re.IGNORECASE)
