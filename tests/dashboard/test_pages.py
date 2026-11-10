"""Which front end `/` serves: the React build when there is one, the classic page otherwise,
and the classic page at `/classic/` either way, all under the same guards."""

import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from mulebox.dashboard import pages
from mulebox.dashboard.server import CSP, build_app
from tests.dashboard.conftest import NOW


@pytest.fixture
def serve(data, hub, tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>classic</title>", encoding="utf-8")
    (static / "style.css").write_text("body{}", encoding="utf-8")

    def run(fn, built):
        if built:
            assets = tmp_path / "app" / "assets"
            assets.mkdir(parents=True)
            (tmp_path / "app" / "index.html").write_text("<!doctype html><title>react</title>", encoding="utf-8")
            (assets / "index-abc.js").write_text("export {};", encoding="utf-8")

        async def main():
            app = build_app(data, hub, clock=lambda: NOW, start_hub=False, static_dir=static)
            async with TestClient(TestServer(app)) as client:
                return await fn(client)
        return asyncio.run(main())
    return run


async def fetch(client, path, **options):
    reply = await client.get(path, **options)
    return reply.status, await reply.text(), reply.headers


def test_without_a_build_the_classic_page_is_the_page(serve):
    async def go(client):
        return [await fetch(client, path) for path in ("/", "/classic/", "/static/style.css", "/app/index.html")]
    root, classic, style, app = serve(go, built=False)
    assert root[0] == 200 and "classic" in root[1]
    assert classic[0] == 200 and "classic" in classic[1]
    assert style[0] == 200
    assert app[0] == 404


def test_with_a_build_the_react_app_is_the_page_and_classic_stays(serve):
    async def go(client):
        return [await fetch(client, path) for path in ("/", "/classic/", "/static/style.css",
                                                        "/app/assets/index-abc.js", "/app/assets/none.js")]
    root, classic, style, script, missing = serve(go, built=True)
    assert root[0] == 200 and "react" in root[1]
    assert classic[0] == 200 and "classic" in classic[1]
    assert style[0] == 200 and script[0] == 200 and "javascript" in script[2]["Content-Type"]
    assert missing[0] == 404


@pytest.mark.parametrize("built", [False, True])
def test_every_page_and_file_keeps_the_guards(serve, built):
    paths = ["/", "/classic/", "/static/style.css"] + (["/app/assets/index-abc.js"] if built else [])

    async def go(client):
        good = [await fetch(client, path) for path in paths]
        bad = [await fetch(client, path, headers={"Host": "evil.example"}) for path in paths]
        return good, bad
    good, bad = serve(go, built=built)
    for status, _, headers in good:
        assert status == 200
        assert headers["Content-Security-Policy"] == CSP
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Cache-Control"] == "no-cache"
    assert [status for status, _, _ in bad] == [421] * len(paths)


def test_the_policy_lets_the_bundled_fonts_load_and_nothing_from_elsewhere():
    assert "font-src 'self'" in CSP and "default-src 'none'" in CSP
    assert "unsafe" not in CSP and "data:" not in CSP and "http" not in CSP


def test_the_app_folder_is_the_one_beside_the_classic_files(tmp_path):
    assert pages.app_dir_for(tmp_path / "static") == tmp_path / "app"
    assert not pages.has_app(tmp_path / "app") and not pages.has_app(None)


def test_a_way_out_of_the_app_folder_is_refused(serve, tmp_path):
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")

    async def go(client):
        return await fetch(client, "/app/%2e%2e/secret.txt")
    assert serve(go, built=True)[0] in (403, 404)
