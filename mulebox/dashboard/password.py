"""The `lan` mode password: scrypt hashing and its file. Only the hash is ever stored."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from pathlib import Path

from mulebox.dashboard.lanfiles import LanNotReady, write_private

MIN_LENGTH = 10
MAX_LENGTH = 1024  # also bounds what a login attempt can make scrypt work on
_N, _R, _P = 2 ** 15, 8, 1
_MAXMEM = 64 * 1024 * 1024
_PREFIX = "scrypt"
FILE_NAME = "password"


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32,
                          maxmem=_MAXMEM)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return "$".join((_PREFIX, str(_N), str(_R), str(_P), _b64(salt),
                     _b64(_derive(password, salt, _N, _R, _P))))


def verify(password: str, stored: str) -> bool:
    """True when `password` matches `stored`. Slow on purpose: call it off the event loop."""
    if len(password) > MAX_LENGTH:
        return False
    try:
        prefix, n, r, p, salt, expected = stored.split("$")
        if prefix != _PREFIX:
            return False
        actual = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except ValueError:
        return False


def check_new(password: str) -> str | None:
    """Why `password` cannot be used, or None."""
    if len(password) < MIN_LENGTH:
        return f"the password needs at least {MIN_LENGTH} characters"
    if len(password) > MAX_LENGTH:
        return f"the password can have at most {MAX_LENGTH} characters"
    return None


def save(directory: Path, password: str) -> Path:
    path = directory / FILE_NAME
    write_private(path, hash_password(password) + "\n")
    return path


def load(directory: Path) -> str:
    path = directory / FILE_NAME
    try:
        stored = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise LanNotReady("no dashboard password yet; run `mulebox dashboard password`"
                          ) from None
    if not stored.startswith(f"{_PREFIX}$") or stored.count("$") != 5:
        raise LanNotReady(f"{path} is not a password file; run `mulebox dashboard password`")
    return stored
