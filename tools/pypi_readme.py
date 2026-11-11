#!/usr/bin/env python3
"""Points the README's relative links at GitHub, for its copy on PyPI.

PyPI shows the README as the project's page, but has none of the repository's files, so a
relative link or image there leads nowhere. The release workflow runs this before it builds the
wheel: links go to the file at the release's tag, images to its raw file. The README in git keeps
its relative links, which work on GitHub, in forks and on branches.
Run from a checkout: `python3 tools/pypi_readme.py v1.1.0` rewrites README.md in place.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGES = "https://github.com/typerhack/mulebox/blob/{tag}/"
FILES = "https://raw.githubusercontent.com/typerhack/mulebox/{tag}/"
_LINK = re.compile(r"(\]\(|(?:src|srcset|href)=\")(?!https?:|#|mailto:)([^)\"\s]+)")
_IMAGE = re.compile(r"\.(png|svg|jpe?g|gif|webp)$", re.I)


def absolute(text: str, tag: str) -> str:
    def point(found: re.Match[str]) -> str:
        path = found[2]
        base = FILES if _IMAGE.search(path.split("#")[0]) else PAGES
        return found[1] + base.format(tag=tag) + path.removeprefix("./")
    return _LINK.sub(point, text)


if __name__ == "__main__":
    readme = REPO / "README.md"
    readme.write_text(absolute(readme.read_text(encoding="utf-8"), sys.argv[1]), encoding="utf-8")
