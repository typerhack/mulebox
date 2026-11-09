"""Make text safe to leave for a public place: redaction plus removing who and where.

`redact.py` removes secrets. This removes what identifies a person or a project: names it
is told about (longest first, also inside longer words such as an env name), and home folders,
email addresses, user@host targets, IP addresses and links wherever they appear. Kept, as they say
nothing of anybody: loopback addresses, links to public package registries and toolchain sites,
and `package@1.2.3`. It leans towards removing too much, and it is idempotent, so running
it twice is how `feedback post` proves that a reviewed draft gained nothing private.

It cannot recognise private code or text it has no name for. That is why a person or agent
reads the draft before it is posted, and why log text is only included on request.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from mulebox.common.redact import Redactor

MIN_NAME_LEN = 3
PLACEHOLDER = "[private]"
# Words too common to identify a project, and the placeholders themselves: a project named
# "private" must not turn "[private]" into "[[private]]" on the second pass. `github` is the
# client name of every CI slot, and the name of a public host, not of anybody.
COMMON_WORDS = frozenset({"mulebox", "main", "master", "head", "check", "test", "run", "job",
                          "private", "url", "email", "address", "redacted", "ssh-target",
                          "github"})
# Public hosts whose links say nothing of who wrote a report: package registries and the
# download sites of toolchains. Their paths still go through the name scrub. A code host is not
# here: a link on it names an owner and a repository.
PUBLIC_HOSTS = frozenset({
    "registry.npmjs.org", "www.npmjs.com", "registry.yarnpkg.com", "pypi.org",
    "files.pythonhosted.org", "repo.packagist.org", "packagist.org", "nodejs.org",
    "registry-1.docker.io", "hub.docker.com", "docs.docker.com", "deb.debian.org",
    "archive.ubuntu.com", "security.ubuntu.com", "cdn.playwright.dev", "playwright.azureedge.net",
})
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]{0,31}://([^\s<>\"')\]/:@]+)[^\s<>\"')\]]*")
_LOOPBACK = re.compile(r"(?:127(?:\.\d{1,3}){3}|0\.0\.0\.0)\b")
# `name@1.2.3` and `name@latest` are packages, not a user at a host; four numbers are an address.
_PACKAGE_AT = r"(?!\d+\.\d+\.\d+(?:[-+][\w.]+)?\b(?!\.\d)|(?:latest|next|beta|canary)\b)"
# (kind, pattern, replacement); kind is how `findings` names a match.
_FIXED = (
    ("email address", re.compile(r"\b[\w.+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"),
     "[email]"),
    ("user at a host", re.compile(rf"\b[\w.-]{{1,64}}@{_PACKAGE_AT}[\w.-]{{1,253}}\b"), "[ssh-target]"),
    ("home folder", re.compile(r"(?:/Users|/home)/[^/\s:'\"]+"), "~"),
    ("IP address", re.compile(r"\b(?!127\.|0\.0\.0\.0\b)\d{1,3}(?:\.\d{1,3}){3}\b"), "[address]"),
    ("network address", re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b"), "[address]"),
)


def _url(match: re.Match) -> str:
    return match[0] if match[1].lower() in PUBLIC_HOSTS else "[url]"


class Anonymizer:
    def __init__(self, names: Iterable[str] = ()) -> None:
        self._redactor = Redactor()
        wanted = {name.strip() for name in names if name}
        kept = sorted((n for n in wanted if len(n) >= MIN_NAME_LEN
                       and n.lower() not in COMMON_WORDS), key=len, reverse=True)
        self._names = None
        if kept:
            words = "|".join(re.escape(name) for name in kept)
            self._names = re.compile(rf"(?<![A-Za-z0-9])(?:{words})(?![A-Za-z0-9])", re.I)

    def _steps(self) -> list[tuple[str, Callable[[str], str]]]:
        """Each kind of thing removed, in order, as (kind, function of the text)."""
        steps: list[tuple[str, Callable[[str], str]]] = [
            ("secret", self._redactor.redact), ("link", lambda text: _URL.sub(_url, text))]
        steps += [(kind, lambda text, p=pattern, r=repl: p.sub(r, text))
                  for kind, pattern, repl in _FIXED]
        if self._names:
            steps.append(("name of a person, project or machine",
                          lambda text: self._names.sub(PLACEHOLDER, text)))
        return steps

    def scrub(self, text: str) -> str:
        for _, step in self._steps():
            text = step(text)
        return text

    def findings(self, text: str) -> list[tuple[int, str]]:
        """(line number, what was found) for each line the scrub would change, so a refusal can
        say what to look at. Only the kind is named, never the value: it is what was private."""
        found = []
        for number, line in enumerate(text.splitlines(), 1):
            kinds = []
            for kind, step in self._steps():
                changed = step(line)
                if changed != line and kind not in kinds:
                    kinds.append(kind)
                line = changed
            if kinds:
                found.append((number, ", ".join(kinds)))
        return found
