"""Time-sortable identifiers: ``<prefix>-<ULID>``.

A ULID is 128 bits: a 48-bit Unix timestamp in milliseconds followed by 80 random bits
from :mod:`secrets`, written as 26 characters of Crockford base32 (uppercase, no I, L,
O, U). Ids therefore sort by creation time to the millisecond.

Choices where docs/interfaces.md is silent:

- Ids are not monotonic within one millisecond: two ids from the same millisecond are
  ordered randomly. Monotonic generation would need module-level state, which the
  interface rules forbid outside loggers.
- A prefix is a lowercase ASCII letter followed by lowercase letters or digits (``job``,
  ``att``, ``wrk``, ``sub``, ``req``). It never contains ``-``, so an id splits
  unambiguously at its last ``-``.
- Validation is strict: the ULID part must be canonical uppercase Crockford base32 and
  its first character at most ``7`` (larger values overflow 128 bits).
- Programming errors (bad prefix, malformed id passed to :func:`id_timestamp`) raise
  :class:`ValueError`, not a :class:`~mulebox.common.errors.MuleboxError`.
"""

from __future__ import annotations

import re
import secrets
import time
from datetime import UTC, datetime, timedelta

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_LENGTH = 26
_TIME_CHARS = 10
_MAX_TIMESTAMP_MS = (1 << 48) - 1
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

_PREFIX_RE = re.compile(r"[a-z][a-z0-9]*")
_ULID_RE = re.compile(rf"[0-7][{CROCKFORD_ALPHABET}]{{{ULID_LENGTH - 1}}}")


def _encode(value: int, length: int) -> str:
    """Encode a non-negative integer as fixed-length Crockford base32."""
    chars = []
    for _ in range(length):
        chars.append(CROCKFORD_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def _decode(text: str) -> int:
    """Decode canonical Crockford base32 text to an integer."""
    value = 0
    for char in text:
        value = (value << 5) | CROCKFORD_ALPHABET.index(char)
    return value


def _check_prefix(prefix: str) -> None:
    if not isinstance(prefix, str) or not _PREFIX_RE.fullmatch(prefix):
        raise ValueError(f"invalid id prefix {prefix!r}: use lowercase letters and digits")


def new_ulid(timestamp_ms: int | None = None) -> str:
    """Return a 26-character ULID for ``timestamp_ms`` (default: now)."""
    if timestamp_ms is None:
        timestamp_ms = time.time_ns() // 1_000_000
    if not 0 <= timestamp_ms <= _MAX_TIMESTAMP_MS:
        raise ValueError(f"timestamp out of ULID range: {timestamp_ms}")
    value = (timestamp_ms << 80) | secrets.randbits(80)
    return _encode(value, ULID_LENGTH)


def new_id(prefix: str) -> str:
    """Return a new id such as ``job-01JC3X...`` (26-character ULID after the dash)."""
    _check_prefix(prefix)
    return f"{prefix}-{new_ulid()}"


def _split(value: str) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    prefix, sep, ulid = value.rpartition("-")
    if not sep or not _PREFIX_RE.fullmatch(prefix) or not _ULID_RE.fullmatch(ulid):
        return None
    return prefix, ulid


def is_valid_id(value: str, prefix: str | None = None) -> bool:
    """True if ``value`` is a well-formed id, with the given prefix when one is passed."""
    parts = _split(value)
    if parts is None:
        return False
    return prefix is None or parts[0] == prefix


def id_timestamp(value: str) -> datetime:
    """Return the creation time embedded in an id, as an aware UTC datetime."""
    parts = _split(value)
    if parts is None:
        raise ValueError(f"not a valid mulebox id: {value!r}")
    timestamp_ms = _decode(parts[1][:_TIME_CHARS])
    try:
        return _EPOCH + timedelta(milliseconds=timestamp_ms)
    except OverflowError:
        raise ValueError(f"id timestamp beyond year 9999: {value!r}") from None
