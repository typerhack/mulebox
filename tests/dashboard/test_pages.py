"""What `/` serves: the React build when there is one, a 503 page that says how to get one
otherwise, all under the same guards. The classic page is gone, and so are its routes."""

import asyncio
import re
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from mulebox.dashboard import login, pages
from mulebox.dashboard.server import CSP, build_app
from tests.dashboard.conftest import NOW, fake_app

WEB = Path(__file__).resolve().parents[2] / "web"


@pytest.fixture
def serve(data, hub, tmp_path):
    def run(fn, built):
        folder = fake_app(tmp_path / "app") if built else tmp_path / "app"

        async def main():
            app = build_app(data, hub, clock=lambda: NOW, start_hub=False, app_dir=folder)
            async with TestClient(TestServer(app)) as client:
                return await fn(client)
        return asyncio.run(main())
    return run


async def fetch(client, path, **options):
    reply = await client.get(path, **options)
    return reply.status, await reply.text(), reply.headers


def test_without_a_build_the_page_says_how_to_build_it_and_the_api_works(serve):
    async def go(client):
        return [await fetch(client, path) for path in ("/", "/api/queue", "/healthz", "/app/index.html")]
    root, api, health, app = serve(go, built=False)
    assert root[0] == 503 and "text/html" in root[2]["Content-Type"]
    assert "npm run build" in root[1] and "web/" in root[1] and "release" in root[1]
    assert root[2]["Content-Security-Policy"] == CSP and root[2]["Cache-Control"] == "no-store"
    assert "<script" not in root[1] and "style" not in root[1]
    assert api[0] == 200 and health[0] == 200
    assert app[0] == 404


def test_with_a_build_the_react_app_is_the_page(serve):
    async def go(client):
        return [await fetch(client, path) for path in ("/", "/app/assets/index-abc.js", "/app/assets/none.js")]
    root, script, missing = serve(go, built=True)
    assert root[0] == 200 and "react" in root[1]
    assert script[0] == 200 and "javascript" in script[2]["Content-Type"]
    assert missing[0] == 404


@pytest.mark.parametrize("built", [False, True])
def test_the_classic_routes_are_gone(serve, built):
    async def go(client):
        return [(await fetch(client, path))[0] for path in ("/classic/", "/static/style.css", "/static/app.js")]
    assert serve(go, built=built) == [404, 404, 404]


@pytest.mark.parametrize("built", [False, True])
def test_every_page_and_file_keeps_the_guards(serve, built):
    paths = ["/"] + (["/app/assets/index-abc.js", "/app/login.css"] if built else [])

    async def go(client):
        good = [await fetch(client, path) for path in paths]
        bad = [await fetch(client, path, headers={"Host": "evil.example"}) for path in paths]
        return good, bad
    good, bad = serve(go, built=built)
    for status, _, headers in good:
        assert status == (200 if built else 503)
        assert headers["Content-Security-Policy"] == CSP
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Cache-Control"] == ("no-cache" if built else "no-store")
    assert [status for status, _, _ in bad] == [421] * len(paths)


def test_the_policy_lets_the_bundled_fonts_load_and_nothing_from_elsewhere():
    assert "font-src 'self'" in CSP and "default-src 'none'" in CSP
    assert "unsafe" not in CSP and "data:" not in CSP and "http" not in CSP


def test_the_app_folder_is_the_one_in_the_package(tmp_path):
    assert pages.APP_DIR == Path(pages.__file__).with_name("app")
    assert not pages.has_app(tmp_path / "app") and not pages.has_app(None)


def test_a_way_out_of_the_app_folder_is_refused(serve, tmp_path):
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")

    async def go(client):
        return await fetch(client, "/app/%2e%2e/secret.txt")
    assert serve(go, built=True)[0] in (403, 404)


def test_only_the_sign_in_page_and_what_it_loads_are_public():
    assert login.is_public("/login") and login.is_public("/app/login.css")
    assert login.is_public("/app/fonts/geist-latin-wght-normal.woff2")
    for path in ("/", "/app/index.html", "/app/login.html", "/app/assets/index-abc.js",
                 "/app/fonts/../index.html", "/app/fontsx/a", "/api/queue", "/static/style.css"):
        assert not login.is_public(path), path


@pytest.mark.skipif(not (WEB / "login.html").is_file(), reason="no web/ beside the package")
def test_the_sign_in_source_works_under_the_policy_and_keeps_its_contract():
    page = (WEB / "login.html").read_text(encoding="utf-8")
    assert login.MARKER in page and 'action="/login"' in page and 'name="password"' in page
    assert "<script" not in page and "style=" not in page and not re.search(r"\son\w+=", page)
    assert "http://" not in page and "https://" not in page
    assert 'href="/src/login/login.css"' in page
    config = (WEB / "vite.config.ts").read_text(encoding="utf-8")
    assert '"login.css"' in config and '"fonts/[name][extname]"' in config  # PUBLIC_PATHS' names
