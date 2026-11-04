"""Make text safe to leave for a public place: redaction plus removing who and where.

`redact.py` removes secrets. This removes what identifies a person or a project: names it
is told about (longest first), and home folders, email addresses, IP addresses and URLs
wherever they appear. It leans towards removing too much, and it is idempotent, so running
it twice is how `feedback post` proves that a reviewed draft gained nothing private.

It cannot recognise private code or text it has no name for. That is why a person or agent
reads the draft before it is posted, and why log text is only included on request.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from mulebox.common.redact import Redactor

MIN_NAME_LEN = 3
PLACEHOLDER = "[private]"
# Words too common to identify a project, and the placeholders themselves: a project named
# "private" must not turn "[private]" into "[[private]]" on the second pass.
COMMON_WORDS = frozenset({"mulebox", "main", "master", "head", "check", "test", "run", "job",
                          "private", "url", "email", "address", "redacted", "ssh-target"})
_FIXED = (
    (re.compile(r"[A-Za-z][A-Za-z0-9+.-]{0,31}://[^\s<>\"')\]]+"), "[url]"),
    (re.compile(r"\b[\w.+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"), "[email]"),
    (re.compile(r"\b[\w.-]{1,64}@[\w.-]{1,253}\b"), "[ssh-target]"),
    (re.compile(r"(?:/Users|/home)/[^/\s:'\"]+"), "~"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "[address]"),
    (re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b"), "[address]"),
)


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

    def scrub(self, text: str) -> str:
        text = self._redactor.redact(text)
        for pattern, replacement in _FIXED:
            text = pattern.sub(replacement, text)
        return self._names.sub(PLACEHOLDER, text) if self._names else text
