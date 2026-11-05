"""Which worktree paths never leave the laptop (docs/interfaces-m1.md, Client).

A pattern is matched against a path relative to the project root, written with `/`:

- `name/` (trailing slash) matches a directory: any parent directory of the path.
- A pattern without a `/` (such as `.env`, `.env.*`, `*.pem`) is a glob matched against
  every path component, so it excludes a file of that name and everything inside a
  directory of that name, at any depth.
- A pattern with a `/` inside (such as `docs/private/*.md`) is a glob matched against the
  whole path and against each leading part of it, so a matching directory excludes its
  contents. A leading `/` is ignored: patterns are always relative to the project root.

One exception: a template such as `.env.example`, tracked in git, passes the built-in `.env.*`
rule. A project builds its real `.env` from it, and being tracked means it already leaves
this machine with every push. An untracked one stays here, and `exclude` still applies.

Matching ignores case: on a case-insensitive filesystem `.ENV` is the same file as `.env`,
and excluding too much is always the safe direction. Globs use fnmatch syntax, where `*`
also matches `/` in whole-path patterns.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase

ENV_RULE = ".env.*"
ENV_TEMPLATES = frozenset({".env.example", ".env.sample", ".env.template", ".env.dist"})

BUILTIN_EXCLUDES: tuple[str, ...] = (
    ".secret/",
    ".env",
    ENV_RULE,
    "secrets/",
    ".npmrc",
    ".envrc",
    ".netrc",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    "id_dsa*",
    "*.p12",
    "*.pfx",
    ".git-credentials",
    ".pypirc",
    ".ssh/",
    ".aws/",
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
        builtin = (p for p in BUILTIN_EXCLUDES if p != ENV_RULE)
        compiled = (_compile(p) for p in (*builtin, *extra))
        self._patterns = tuple(p for p in compiled if p is not None)
        self._env_rule = _compile(ENV_RULE)

    def excluded(self, relpath: str, tracked: bool = False) -> bool:
        """True if `relpath` (relative, `/`-separated) must not be sent.

        `tracked` says git tracks the file, which lets an env template through.
        """
        parts = [p for p in relpath.lower().split("/") if p not in ("", ".")]
        if not parts:
            return True
        if any(p.matches(parts) for p in self._patterns):
            return True
        template = tracked and parts[-1] in ENV_TEMPLATES
        return self._env_rule.matches(parts[:-1] if template else parts)
