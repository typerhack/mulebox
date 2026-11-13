"""Lines in a job's output that say something is downloading, and how far it has got.

Pure: one line in, one `Seen` out (or None). Read by common/download_watch.py for agent jobs
(worker/logtail.py) and GitHub runs (runners/live_log.py). The shapes, each checked against real
output or the tool's own source:

- GitHub's cache (actions/cache, and setup-python and setup-node with `cache:`), seen on the
  node: `Cache hit for: <key>`, then `Received 1418315 of 9806923 (14.5%), 0.1 MBs/sec` about
  every second, `Cache Size: ~9 MB (9918658 B)` once it is all there, and one of
  `Cache restored successfully`, `Cache not found for input keys: ...` or
  `##[warning]Failed to restore: ...` at the end. The key names the package manager.
- A tool into the runner's tool cache: setup-python's `Download from "<url>"`, setup-node's
  `Acquiring 22.12.0 - x64 from <url>`; the tool cache prints no progress, so these give a name
  and no bytes, and end at `Extract...`, `Adding to the cache` or `Successfully set up`.
- pnpm, for a large package: `Downloading next@16.4.3: 48.31 kB/43.60 MB`, ending `, done`.
- pip and uv: `Downloading torch-2.5.1-cp312-...whl (906.4 MB)` as a file starts (no progress
  without a terminal), uv's `Downloaded torch` as it ends; pip's `Installing collected packages`
  ends it too.
- Playwright: `Downloading Chromium 131.0 (playwright build v1148) from https://...`, then
  without a terminal `|■■■■■■■■      |  10% of 164.7 MiB` every tenth, and
  `Chromium 131.0 (playwright build v1148) downloaded to /path` at the end.

Image layers are counted by worker/pullnoise.py, which feeds its totals in directly. Not
understood: git's `Receiving objects`, curl and wget meters (they redraw a line, which a log
without a terminal does not show), and Gradle or Maven, which print no sizes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CACHE, TOOL, PACKAGE, BROWSER, IMAGE, NETWORK = "cache", "tool", "package", "browser", "image", "network"
START, PROGRESS, END = "start", "progress", "end"
MAX_NAME = 80
SIZE = r"(\d+(?:\.\d+)?)\s*([kKMGT]?i?B)"
_MANAGERS = ("pnpm", "npm", "yarn", "pip", "pipenv", "poetry", "go", "gradle", "maven", "sbt")

_RECEIVED = re.compile(r"^Received (\d+) of (\d+) \([\d.]+%\), [\d.]+ MBs/sec\s*$")
_CACHE_SIZE = re.compile(r"^Cache Size: ~\d+ MB \((\d+) B\)\s*$")
_CACHE_HIT = re.compile(r"^Cache hit for(?: restore-key)?: (\S+)")
_CACHE_END = re.compile(r"^(?:##\[warning\])?(?:Cache restored successfully|Cache restored from key:|"
                        r"Cache not found for input keys:|Failed to restore:)")
_TOOL_URL = re.compile(r'^(?:Download from "(https://[^"]+)"|Acquiring \S+ - \S+ from (https://\S+))\s*$')
_TOOL_END = re.compile(r"^(?:Extract|Adding to the cache|Successfully set up)")
_PNPM = re.compile(rf"^Downloading (\S+): {SIZE}\s*/\s*{SIZE}(, done)?\s*$")
_FILE = re.compile(rf"^\s*Downloading (\S+) \({SIZE}\)\s*$")
_FILE_END = re.compile(r"^\s*(?:Downloaded \S+\s*$|Installing collected packages)")
_BROWSER = re.compile(r"^Downloading (.+?) from https://\S+\s*$")
_BROWSER_STEP = re.compile(r"^\|[■\s]*\|\s*(\d{1,3})% of ([\d.]+) MiB\s*$")
_BROWSER_END = re.compile(r"^(.+?) downloaded to /\S*\s*$")
_FIRST = frozenset("RCDAF#ESI|")  # the first character of every shape but the browser's end


@dataclass(frozen=True)
class Seen:
    kind: str  # START, PROGRESS or END
    what: str  # CACHE, TOOL, PACKAGE, BROWSER (IMAGE comes from pullnoise.py)
    name: str | None = None
    done: int | None = None
    total: int | None = None


def size_bytes(number: str, unit: str) -> int:
    """`12.3` `MB` -> bytes; `KiB` and the like count in 1024s."""
    base = 1024 if "i" in unit else 1000
    power = {"": 0, "k": 1, "K": 1, "M": 2, "G": 3, "T": 4}[unit.rstrip("B").rstrip("i")]
    return int(float(number) * base**power)


def short(name: str) -> str:
    """A file name from a URL or path, cut to MAX_NAME."""
    name = name.rstrip("/").rsplit("/", 1)[-1] or name
    return name[:MAX_NAME]


def cache_name(key: str) -> str:
    """`pip cache` from setup-python's key, `npm cache` from setup-node's, else `cache`."""
    parts = key.lower().split("-")
    for manager in _MANAGERS:
        if manager in parts:
            return f"{manager} cache"
    return CACHE


def parse(line: str) -> Seen | None:
    text = line.strip()
    if not text:
        return None
    if " downloaded to " in text:
        found = _BROWSER_END.match(text)
        return Seen(END, BROWSER, found[1][:MAX_NAME]) if found else None
    if text[0] not in _FIRST:
        return None
    return _cache(text) or _tool(text) or _package(text) or _browser(text)


def _cache(text: str) -> Seen | None:
    if found := _RECEIVED.match(text):
        return Seen(PROGRESS, CACHE, None, int(found[1]), int(found[2]))
    if found := _CACHE_SIZE.match(text):
        return Seen(PROGRESS, CACHE, None, int(found[1]), int(found[1]))
    if found := _CACHE_HIT.match(text):
        return Seen(START, CACHE, cache_name(found[1]))
    if _CACHE_END.match(text):
        return Seen(END, CACHE)
    return None


def _tool(text: str) -> Seen | None:
    if found := _TOOL_URL.match(text):
        return Seen(START, TOOL, short(found[1] or found[2]))
    if _TOOL_END.match(text):
        return Seen(END, TOOL)
    return None


def _package(text: str) -> Seen | None:
    if found := _PNPM.match(text):
        total = size_bytes(found[4], found[5])
        done = total if found[6] else size_bytes(found[2], found[3])
        return Seen(END if found[6] else PROGRESS, PACKAGE, short(found[1]), done, total)
    if found := _FILE.match(text):
        return Seen(START, PACKAGE, short(found[1]), None, size_bytes(found[2], found[3]))
    if _FILE_END.match(text):
        return Seen(END, PACKAGE)
    return None


def _browser(text: str) -> Seen | None:
    if found := _BROWSER_STEP.match(text):
        total = int(float(found[2]) * 1024 * 1024)
        return Seen(PROGRESS, BROWSER, None, total * min(100, int(found[1])) // 100, total)
    if found := _BROWSER.match(text):
        return Seen(START, BROWSER, found[1][:MAX_NAME])
    return None
