"""Builds the dashboard's React front end before a wheel is made from a checkout.

The front end lives in `web/` at the repository root and builds into `mulebox/dashboard/app/`,
static files the dashboard serves (dashboard/pages.py). A build machine never needs Node: the
laptop that runs `mulebox setup` builds, when it can.

- No `web/` beside the package (an install from PyPI): nothing to do; the package already
  holds whatever build it was shipped with.
- The build is there and newer than every source file: nothing to do, npm or not.
- Otherwise it is built, which needs Node.js and npm; without them this stops with how to get
  them, as a wheel with no page or an old one would install a dashboard that does not match.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from mulebox.common.errors import MuleboxError

SOURCES = ("src", "public", "package.json", "package-lock.json", "index.html", "login.html",
           "vite.config.ts")
NO_NPM = ("the dashboard's front end in web/ is {state} and npm is not on the PATH. Install "
          "Node.js (it comes with npm; https://nodejs.org or your package manager, such as "
          "`brew install node` or `apt install nodejs npm`), then run this again; or build it "
          "yourself with `npm ci` and `npm run build` in web/")


class WebBuildError(MuleboxError):
    """The web build could not run or failed; the wheel must not go out without its page."""


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
           run: Callable[..., object] = subprocess.run) -> str:
    """Build `web/` into `package`'s dashboard when needed. Returns what happened:
    `absent`, `fresh` or `built`; raises WebBuildError with no npm or a failed build."""
    web = package.parent / "web"
    if not (web / "package.json").is_file():
        return "absent"
    out = package / "dashboard" / "app"
    if not stale(web, out):
        return "fresh"
    npm = which("npm")
    if npm is None:
        state = "out of date" if (out / "index.html").is_file() else "not built"
        raise WebBuildError(NO_NPM.format(state=state))
    try:
        if not (web / "node_modules").is_dir():
            run([npm, "ci", "--no-audit", "--no-fund"], cwd=web, check=True, capture_output=True, text=True)
        run([npm, "run", "build"], cwd=web, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as failed:
        detail = (failed.stderr or failed.stdout or "").strip().splitlines()[-5:]
        raise WebBuildError("the dashboard's web build failed (`npm run build` in web/):\n"
                            + "\n".join(detail)) from None
    return "built"
