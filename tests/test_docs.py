"""The docs a new user reads: links lead somewhere, and the commands they name exist."""

import re
from pathlib import Path

import pytest

from mulebox.cli import build_parser

REPO = Path(__file__).resolve().parent.parent
PAGES = [REPO / "README.md", *sorted((REPO / "docs").glob("*.md"))]
USER_PAGES = ("README.md", "getting-started.md", "install.md", "troubleshooting.md",
              "releasing.md")
LINK = re.compile(r"\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```.*?^```", re.S | re.M)


def anchors(page: Path) -> set[str]:
    """GitHub's anchors for a page's headings, and explicit `<a id>` ones. A heading that repeats
    gets `-1`, `-2`, ... on GitHub, in page order (README has two "The dashboard")."""
    text = FENCE.sub("", page.read_text(encoding="utf-8"))
    found = set(re.findall(r'<a id="([^"]+)"', text))
    seen: dict[str, int] = {}
    for title in re.findall(r"^#+ (.+)$", text, re.M):
        slug = re.sub(r"[^\w\- ]", "", title.lower().replace("`", "")).replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        found.add(f"{slug}-{count}" if count else slug)
    return found


def local_links(page: Path) -> list[str]:
    links = LINK.findall(FENCE.sub("", page.read_text(encoding="utf-8")))
    return [link for link in links if not re.match(r"[a-z]+:", link)]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_links_reach_a_file_and_a_heading(page):
    for link in local_links(page):
        name, _, anchor = link.partition("#")
        target = (page.parent / name).resolve() if name else page
        assert target.exists(), f"{page.name}: {link}"
        if anchor and target.suffix == ".md":
            assert anchor in anchors(target), f"{page.name}: {link}"


@pytest.mark.parametrize("name", USER_PAGES)
def test_commands_they_name_exist(name):
    page = REPO / name if name == "README.md" else REPO / "docs" / name
    known = set(build_parser()._subparsers._group_actions[0].choices)
    text = page.read_text(encoding="utf-8")
    named = set(re.findall(r"`(?:\S*/)?mulebox ([a-z][a-z-]*)", text))
    for code in FENCE.findall(text):
        named |= set(re.findall(r"^\s*(?:\S*/)?mulebox ([a-z][a-z-]*)", code, re.M))
    assert named <= known, named - known


def test_the_user_pages_use_no_roadmap_codes():
    """`M2` means nothing to a new user. The link to the roadmap may say which task."""
    for name in USER_PAGES:
        page = REPO / name if name == "README.md" else REPO / "docs" / name
        text = page.read_text(encoding="utf-8")
        assert not re.search(r"\bin M\d\b|\(M\d\)", text), name
