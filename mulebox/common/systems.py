"""Which system a job runs on: Linux or macOS (design.md, Which node runs a job; M25.6).

A project's jobs were set up for one system: its packages, scripts and containers. A job of a
Linux project taken by a Mac node can fail there for no fault of its code (seen 2026-11-14: a
`node_modules` installed on macOS, then run in a Linux container). So:

- Every worker offers its own system as a capability, `linux` or `macos` (compose.py's
  `worker_capabilities`). A worker older than 1.23 does not; the coordinator counts it as macOS
  when it offers Xcode or a simulator, else as Linux (`inferred`), as every node was Linux before.
- A job needs one system (`need`): `os:` in .mulebox.yml (`linux`, `macos`, or `any` for
  either), by default `macos` when it pins Xcode or a simulator and `linux` otherwise. The
  client sends `os:` as written and the coordinator adds the need (`with_system`), so a newer
  client never asks an older coordinator for something its nodes do not report, and the job of
  an older client gets the rule too.

The chip is not part of it: each node installs a project's packages for itself, so a Linux
arm64 node and a Linux x86-64 node run the same project alike.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable

LINUX, MACOS, ANY = "linux", "macos", "any"
SYSTEMS = (LINUX, MACOS)
CHOICES = (LINUX, MACOS, ANY)
_APPLE_ONLY = ("xcode", "simulator")  # config.FOUND_ON_NODE, offered by Mac nodes only


def of(platform: str = sys.platform) -> str | None:
    if platform == "darwin":
        return MACOS
    return LINUX if platform.startswith("linux") else None


def offered(platform: str = sys.platform) -> tuple[str, ...]:
    system = of(platform)
    return (system,) if system else ()


def inferred(capabilities: Iterable[str]) -> list[str]:
    """`capabilities` with a system, for a worker too old to report one."""
    have = list(capabilities)
    if set(have) & set(SYSTEMS):
        return have
    return [*have, MACOS if set(have) & set(_APPLE_ONLY) else LINUX]


def need(asked: str | None, needs: Iterable[str]) -> str | None:
    """The system a job with `needs` runs on, from `os:` (`asked`); None for `any`."""
    if asked == ANY:
        return None
    if asked is not None:
        return asked
    return MACOS if set(needs) & set(_APPLE_ONLY) else LINUX


def with_system(needs: Iterable[str], asked: str | None) -> list[str]:
    """`needs` and the system they run on: the coordinator's rule (coordinator/needs.py), which
    `mulebox doctor` and the contract show the same way."""
    have = list(needs)
    system = need(asked, have)
    return list(dict.fromkeys((*have, *((system,) if system else ()))))


def problem(value: str) -> str | None:
    if value not in CHOICES:
        return f"must be one of {', '.join(CHOICES)}, got {value!r}"
    return None
