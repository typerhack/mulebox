"""Blank out secrets in job logs before they are stored or streamed (docs/design.md).

Redactor replaces known secret values (matched literally, longest first) and built-in
patterns with "[redacted]". Patterns err on the side of redacting too much: a log line
that loses a harmless value is better than a leaked token. Every pattern uses bounded
quantifiers and simple character classes, so matching stays linear in practice.

StreamRedactor does the same for a log arriving in chunks. Hold-back strategy:
- Output is released only up to the last line break (\\n or \\r), because every pattern
  except PEM blocks lives inside one line. The incomplete last line is held back.
- If a known secret contains a line break, the last (longest secret - 1) characters are
  held back as well, so such a secret can never straddle the release point.
- A match that straddles the release point moves the release point to its start; the
  match is found again, whole, on a later feed.
- An unterminated PEM private key block is held back from its BEGIN line until its END
  line arrives (at most PEM_HOLD_CHARS; past that the rest of the buffer is redacted).
- A line longer than MAX_LINE_CHARS is released early except for its last
  STREAM_TAIL_CHARS (or longest secret - 1, if larger), which is longer than the
  shortest text any pattern needs to match.
flush() redacts and returns whatever is still held.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import NamedTuple

REPLACEMENT = "[redacted]"
MIN_SECRET_LEN = 6
MAX_LINE_CHARS = 8192
STREAM_TAIL_CHARS = 1024
PEM_HOLD_CHARS = 32 * 1024

_KEY_WORDS = r"(?:password|passwd|secret|token|api_?key)"

# (compiled pattern, group whose text is replaced; 0 is the whole match)
_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
    # GitHub tokens: classic (ghp_, gho_, ghs_, ghu_, ghr_) and fine-grained.
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,255}|github_pat_[A-Za-z0-9_]{20,255})"), 0),
    # AWS access key ids (long-term and temporary).
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), 0),
    # Authorization headers: keep the scheme, drop the credential.
    (
        re.compile(
            r"(?i)\bauthorization[ \t]{0,4}:[ \t]{0,4}(?:bearer|basic|token)[ \t]{1,8}"
            r"([^\s'\"]{1,1024})"
        ),
        1,
    ),
    # password=..., DB_TOKEN = '...', --secret="..." style assignments.
    (
        re.compile(
            rf"(?i)\b\w{{0,64}}?{_KEY_WORDS}\w{{0,64}}[ \t]{{0,4}}=[ \t]{{0,4}}"
            r"(\"[^\"\r\n]{1,1024}\"|'[^'\r\n]{1,1024}'|[^\s'\"&;,]{1,1024})"
        ),
        1,
    ),
    # JSON style: "password": "...".
    (
        re.compile(
            rf"(?i)\"\w{{0,64}}?{_KEY_WORDS}\w{{0,64}}\"[ \t]{{0,4}}:[ \t]{{0,4}}"
            r"\"([^\"\r\n]{1,1024})\""
        ),
        1,
    ),
    # URLs with credentials: scheme://user:password@host keeps the user.
    (re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]{0,31}://[^\s/:@]{1,256}:([^\s/@]{1,256})@"), 1),
)

# PEM private key blocks; an unterminated block runs to the end of the text.
_PEM = re.compile(
    r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY-----"
    r"(?:[\s\S]*?(?P<end>-----END [A-Z0-9 ]{0,40}PRIVATE KEY-----)|[\s\S]*)"
)


class _Hit(NamedTuple):
    start: int  # whole match, used to decide where a stream may be cut
    end: int
    red_start: int  # the part that is replaced
    red_end: int
    open_pem: bool  # a PEM block without its END line (yet)


class Redactor:
    """Replace known secrets and built-in secret patterns with "[redacted]"."""

    def __init__(self, secrets: Iterable[str] = (), patterns: bool = True) -> None:
        self._secrets: set[str] = set()
        self._secret_re: re.Pattern[str] | None = None
        self._patterns = patterns
        for value in secrets:
            self.add_secret(value)

    def add_secret(self, value: str) -> None:
        """Redact this exact value from now on. Values under 6 characters are ignored."""
        if len(value) < MIN_SECRET_LEN or not value.strip() or value in self._secrets:
            return
        self._secrets.add(value)
        ordered = sorted(self._secrets, key=len, reverse=True)
        # A lookahead finds overlapping occurrences too, so overlapping secrets merge.
        self._secret_re = re.compile("(?=(" + "|".join(re.escape(s) for s in ordered) + "))")

    def redact(self, text: str) -> str:
        return _apply(text, self._hits(text), len(text))

    @property
    def _longest_secret(self) -> int:
        return max(map(len, self._secrets), default=0)

    def _hits(self, text: str) -> list[_Hit]:
        hits = []
        if self._secret_re is not None:
            for m in self._secret_re.finditer(text):
                hits.append(_Hit(*m.span(1), *m.span(1), False))
        if self._patterns:
            for pattern, group in _PATTERNS:
                hits += [_Hit(*m.span(), *m.span(group), False) for m in pattern.finditer(text)]
            for m in _PEM.finditer(text):
                hits.append(_Hit(*m.span(), *m.span(), m.group("end") is None))
        return hits


class StreamRedactor(Redactor):
    """Redactor for text arriving in chunks; see the module docstring for the hold-back."""

    def __init__(self, secrets: Iterable[str] = (), patterns: bool = True) -> None:
        super().__init__(secrets, patterns)
        self._held = ""

    def feed(self, chunk: str) -> str:
        """Add a chunk; return the redacted text that is safe to release now."""
        buf = self._held + chunk
        hits = self._hits(buf)
        cut = self._cut(buf, hits)
        self._held = buf[cut:]
        return _apply(buf, hits, cut)

    def flush(self) -> str:
        """Return everything still held, redacted, and start over."""
        buf, self._held = self._held, ""
        return self.redact(buf)

    def _cut(self, buf: str, hits: list[_Hit]) -> int:
        size = len(buf)
        secret_tail = max(self._longest_secret - 1, 0)
        cut = max(buf.rfind("\n"), buf.rfind("\r")) + 1
        if any("\n" in s or "\r" in s for s in self._secrets):
            cut = min(cut, max(size - secret_tail, 0))
        if size - cut > MAX_LINE_CHARS:
            cut = max(cut, size - max(STREAM_TAIL_CHARS, secret_tail))
        for hit in hits:
            if hit.open_pem:
                if size - hit.start > PEM_HOLD_CHARS:
                    return size  # give up holding; the rest is redacted as key material
                cut = min(cut, hit.start)
        moved = True
        while moved:
            moved = False
            for hit in hits:
                if hit.start < cut < hit.end:
                    cut, moved = hit.start, True
        return cut


def _apply(text: str, hits: list[_Hit], limit: int) -> str:
    """Return text[:limit] with every hit's redacted span inside it replaced."""
    spans = sorted((h.red_start, h.red_end) for h in hits if h.red_end <= limit)
    out, pos = [], 0
    for start, end in spans:
        if end <= pos:
            continue
        if start < pos:  # overlaps the previous span: extend it
            pos = end
            continue
        out += [text[pos:start], REPLACEMENT]
        pos = end
    out.append(text[pos:limit])
    return "".join(out)
