"""Which worktree paths never leave the laptop (docs/interfaces-m1.md, Client).

A pattern is matched against a path relative to the project root, written with `/`:

- `name/` (trailing slash) matches a directory: any parent directory of the path.
- A pattern without a `/` (such as `.env`, `.env.*`, `*.pem`) is a glob matched against
  every path component, so it excludes a file of that name and everything inside a
  directory of that name, at any depth.
- A pattern with a `/` inside (such as `docs/private/*.md`) is a glob matched against the
  whole path and against each leading part of it, so a matching directory excludes its
  contents. A leading `/` is ignored: patterns are always relative to the project root.

Matching ignores case: on a case-insensitive filesystem `.ENV` is the same file as `.env`,
and excluding too much is always the safe direction. Globs use fnmatch syntax, where `*`
also matches `/` in whole-path patterns.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase

BUILTIN_EXCLUDES: tuple[str, ...] = (
    ".secret/",
    ".env",
    ".env.*",
    "secrets/",
    ".npmrc",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    ".mulebox/",
)


@dataclass(frozen=True)
class _Pattern:
    glob: str
    dir_only: bool
    whole_path: bool

    def matches(self, parts: list[str]) -> bool:
        # Candidates: the components (or leading paths) this pattern may match.
        # A directory-only pattern never matches the final component, which is a file.
        last = len(parts) - 1 if self.dir_only else len(parts)
        if self.whole_path:
            return any(fnmatchcase("/".join(parts[: i + 1]), self.glob) for i in range(last))
        return any(fnmatchcase(part, self.glob) for part in parts[:last])


def _compile(pattern: str) -> _Pattern | None:
    text = pattern.strip().lower()
    dir_only = text.endswith("/")
    text = text.strip("/")
    if not text:
        return None
    return _Pattern(glob=text, dir_only=dir_only, whole_path="/" in text)


class Excludes:
    """The built-in secret excludes plus a project's own `exclude` patterns."""

    def __init__(self, extra: Iterable[str] = ()) -> None:
        compiled = (_compile(p) for p in (*BUILTIN_EXCLUDES, *extra))
        self._patterns = tuple(p for p in compiled if p is not None)

    def excluded(self, relpath: str) -> bool:
        """True if `relpath` (relative, `/`-separated) must not be sent."""
        parts = [p for p in relpath.lower().split("/") if p not in ("", ".")]
        if not parts:
            return True
        return any(p.matches(parts) for p in self._patterns)
