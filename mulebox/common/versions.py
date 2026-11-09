"""Comparing mulebox versions (`MAJOR.MINOR.PATCH`, VERSION): one place, so every side agrees."""

from __future__ import annotations

import re

_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse(text: object) -> tuple[int, int, int] | None:
    """The version as numbers, or None when `text` is not one (an editable build, a typo)."""
    found = _VERSION.match(text) if isinstance(text, str) else None
    return (int(found[1]), int(found[2]), int(found[3])) if found else None


def compare(a: object, b: object) -> int | None:
    """-1, 0 or 1 as `a` is older, the same or newer than `b`; None if either is no version."""
    left, right = parse(a), parse(b)
    if left is None or right is None:
        return None
    return (left > right) - (left < right)
