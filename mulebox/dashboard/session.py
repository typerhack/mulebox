"""`lan` mode state: who may connect, signed-in sessions and the login limiter.

Sessions live in memory, so restarting the service signs everyone out (that is also how
a new password takes effect). Only a hash of each token is kept. No aiohttp here.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field

SESSION_TTL_S = 24 * 3600
MAX_SESSIONS = 64
FREE_FAILURES = 5
FIRST_WAIT_S = 30.0
MAX_WAIT_S = 900.0
MAX_TRACKED = 1024


def _key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Sessions:
    def __init__(self, clock: Callable[[], float], ttl: float = SESSION_TTL_S,
                 limit: int = MAX_SESSIONS) -> None:
        self._clock, self._ttl, self._limit = clock, ttl, limit
        self._expires: dict[str, float] = {}

    def create(self) -> str:
        now = self._clock()
        self._expires = {k: end for k, end in self._expires.items() if end > now}
        while len(self._expires) >= self._limit:  # dicts keep order: the oldest goes first
            del self._expires[next(iter(self._expires))]
        token = secrets.token_urlsafe(32)
        self._expires[_key(token)] = now + self._ttl
        return token

    def valid(self, token: str | None) -> bool:
        return bool(token) and self._expires.get(_key(token), 0.0) > self._clock()

    def end(self, token: str | None) -> None:
        if token:
            self._expires.pop(_key(token), None)


class LoginLimiter:
    """Per-address: a few free failures, then a doubling wait up to `MAX_WAIT_S`.

    Per address, not global, so that one device cannot lock everyone else out.
    """

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._failed: dict[str, tuple[int, float]] = {}

    def retry_after(self, who: str) -> float:
        """Seconds until `who` may try again; 0 means now."""
        _, until = self._failed.get(who, (0, 0.0))
        return max(0.0, until - self._clock())

    def failed(self, who: str) -> None:
        count = self._failed.get(who, (0, 0.0))[0] + 1
        over = count - FREE_FAILURES
        wait = min(FIRST_WAIT_S * 2 ** (over - 1), MAX_WAIT_S) if over > 0 else 0.0
        if len(self._failed) >= MAX_TRACKED and who not in self._failed:
            self._failed.clear()
        self._failed[who] = (count, self._clock() + wait)

    def succeeded(self, who: str) -> None:
        self._failed.pop(who, None)


@dataclass
class LanAccess:
    """Everything the TLS listener's rules need."""

    network: ipaddress.IPv4Network
    hosts: frozenset[str]
    listen: tuple[str, int]  # the LAN listener's address and port
    password_hash: str
    sessions: Sessions
    limiter: LoginLimiter
    # One hash at a time: scrypt takes memory and CPU from jobs on the build machine.
    hashing: asyncio.Lock = field(default_factory=asyncio.Lock)

    def is_lan_socket(self, sockname: object) -> bool:
        """True for the LAN listener, and when it is unknown: never assume the open one."""
        if not isinstance(sockname, tuple) or len(sockname) < 2:
            return True
        return sockname[:2] == self.listen

    def allows(self, remote: str | None) -> bool:
        try:
            return ipaddress.ip_address(remote or "") in self.network
        except ValueError:
            return False
