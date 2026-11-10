"""The dashboard's pages and their files: which front end `/` serves.

Two front ends ship in the package. `static/` is the classic page, hand-written modules with no
build step. `app/` is the React front end (`web/` in the repository), built to static files at
release time and by `mulebox setup`; a build machine never needs Node.

- With `app/index.html` present, `/` is the React app and its files are under `/app/`.
- The classic page stays at `/classic/` with its files under `/static/`, so the two can be
  compared until the classic one is retired.
- Without a build (a checkout nobody built, a wheel made without npm), `/` is the classic page.

Every guard of server.py applies to all of it: these are plain GET routes of the same app.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import web

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]
APP_ROUTE = "/app/"
CLASSIC_ROUTE = "/classic/"


def app_dir_for(static_dir: Path) -> Path:
    """Where the React build sits: the folder `app` beside the classic page's folder."""
    return static_dir.with_name("app")


def has_app(app_dir: Path | None) -> bool:
    return app_dir is not None and (app_dir / "index.html").is_file()


def _page(path: Path) -> Handler:
    async def page(request: web.Request) -> web.StreamResponse:
        return web.FileResponse(path)
    return page


def add_routes(app: web.Application, static_dir: Path, app_dir: Path | None) -> None:
    classic = _page(static_dir / "index.html")
    built = has_app(app_dir)
    app.router.add_get("/", _page(app_dir / "index.html") if built and app_dir else classic)
    app.router.add_get(CLASSIC_ROUTE, classic)
    app.router.add_static("/static/", static_dir, follow_symlinks=False)
    if built and app_dir:
        app.router.add_static(APP_ROUTE, app_dir, follow_symlinks=False)
