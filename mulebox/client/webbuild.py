"""Builds the dashboard's React front end before a wheel is made from a checkout.

The front end lives in `web/` at the repository root and builds into `mulebox/dashboard/app/`,
static files the dashboard serves (dashboard/pages.py). A build machine never needs Node: the
laptop that runs `mulebox setup` builds, when it can.

- No `web/` beside the package (a pip install, the binary): nothing to do; the package already
  holds whatever build it was shipped with.
- `npm` not on the PATH: the wheel goes without a fresh build, said in one line.
- Otherwise the build runs when its output is missing or older than any source file.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from mulebox.common.errors import MuleboxError

SOURCES = ("src", "public", "package.json", "package-lock.json", "index.html", "vite.config.ts")
NO_NPM = ("npm not found: the dashboard's new front end is not built, "
          "so the wheel goes with the one it has, or the classic page")


class WebBuildError(MuleboxError):
    """The web build ran and failed; the wheel must not go out with a half-made front end."""


def _newest(web: Path) -> float:
    newest = 0.0
    for name in SOURCES:
        path = web / name
        files = [p for p in path.rglob("*") if p.is_file()] if path.is_dir() else [path]
        newest = max([newest, *(p.stat().st_mtime for p in files if p.exists())])
    return newest


def stale(web: Path, out: Path) -> bool:
    """True when the build is missing or older than any source file."""
    index = out / "index.html"
    return not index.is_file() or index.stat().st_mtime < _newest(web)


def ensure(package: Path, *, which: Callable[[str], str | None] = shutil.which,
           run: Callable[..., object] = subprocess.run,
           say: Callable[[str], None] = print) -> str:
    """Build `web/` into `package`'s dashboard when needed. Returns what happened:
    `absent`, `no-npm`, `fresh` or `built`."""
    web = package.parent / "web"
    if not (web / "package.json").is_file():
        return "absent"
    npm = which("npm")
    if npm is None:
        say(NO_NPM)
        return "no-npm"
    if not stale(web, package / "dashboard" / "app"):
        return "fresh"
    try:
        if not (web / "node_modules").is_dir():
            run([npm, "ci", "--no-audit", "--no-fund"], cwd=web, check=True, capture_output=True, text=True)
        run([npm, "run", "build"], cwd=web, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as failed:
        detail = (failed.stderr or failed.stdout or "").strip().splitlines()[-5:]
        raise WebBuildError("the dashboard's web build failed (`npm run build` in web/):\n"
                            + "\n".join(detail)) from None
    return "built"
