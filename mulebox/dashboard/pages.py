"""The dashboard's page and its files: the React front end, built into `app/`.

The front end lives in `web/` in the repository and is built to static files at release time
and by `mulebox setup` (client/webbuild.py); a build machine never needs Node.

- With `app/index.html` present, `/` is the React app and its files are under `/app/`, the
  sign-in page of `lan` mode among them (`app/login.html`, login.py).
- Without a build (a checkout nobody built), `/` and the sign-in page answer 503 with a short
  page that says how to get one. The API works either way.

Every guard of server.py applies to all of it: these are plain GET routes of the same app.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import web

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]
APP_DIR = Path(__file__).with_name("app")
APP_ROUTE = "/app/"
NOT_BUILT = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>mulebox: dashboard not built</title></head>
<body>
<h1>The dashboard's page is not built</h1>
<p>This mulebox has no front end. The API still answers, and <code>mulebox queue</code> shows
the same data.</p>
<p>To get the page, install a release of mulebox, or build it from a checkout:
<code>npm ci</code> and <code>npm run build</code> in <code>web/</code> (needs Node.js), then
restart the dashboard. <code>mulebox setup</code> does this for a build machine.</p>
</body>
</html>
"""


def has_app(app_dir: Path | None) -> bool:
    return app_dir is not None and (app_dir / "index.html").is_file()


def not_built() -> web.Response:
    return web.Response(text=NOT_BUILT, status=503, content_type="text/html",
                        headers={"Cache-Control": "no-store"})


def _page(path: Path) -> Handler:
    async def page(request: web.Request) -> web.StreamResponse:
        return web.FileResponse(path)
    return page


async def _missing(request: web.Request) -> web.StreamResponse:
    return not_built()


def add_routes(app: web.Application, app_dir: Path) -> None:
    if not has_app(app_dir):
        app.router.add_get("/", _missing)
        return
    app.router.add_get("/", _page(app_dir / "index.html"))
    app.router.add_static(APP_ROUTE, app_dir, follow_symlinks=False)
