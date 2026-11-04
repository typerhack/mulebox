"""The LAN listener on a real socket, plain and over real TLS: the rules are the same."""

import asyncio
import ipaddress
import shutil

import pytest
from aiohttp import ClientSession, CookieJar, TCPConnector
from aiohttp.test_utils import TestClient, TestServer, unused_port
from yarl import URL

from mulebox.dashboard import cert, password
from mulebox.dashboard.login import COOKIE
from mulebox.dashboard.server import LOGIN_CSP, STATIC_DIR, build_app
from mulebox.dashboard.session import FREE_FAILURES, LanAccess, LoginLimiter, Sessions

from .conftest import NOW

PASSWORD = "correct horse"
HOST = "127.0.0.1"


@pytest.fixture(scope="module")
def tls_dir(tmp_path_factory):
    directory = tmp_path_factory.mktemp("lan")
    cert.generate(directory, HOST)
    password.save(directory, PASSWORD)
    return directory


@pytest.fixture(params=["http", "https"])
def lan(request, data, hub, tls_dir, tmp_path):
    """Run `async fn(http, url)` on the LAN listener; `range_` is the allowed network."""
    scheme = request.param
    static = tmp_path / "static"
    static.mkdir()
    for name in ("index.html", "login.html", "style.css"):
        shutil.copy(STATIC_DIR / name, static / name)

    def run(fn, range_="127.0.0.0/8", open_lan=False):
        async def main():
            clock = lambda: NOW  # noqa: E731
            port = unused_port()
            access = LanAccess(ipaddress.ip_network(range_), frozenset({HOST}), (HOST, port),
                               None if open_lan else password.load(tls_dir), Sessions(clock),
                               LoginLimiter(clock))
            app = build_app(data, hub, clock=clock, start_hub=False, static_dir=static, lan=access)
            server = TestServer(app, scheme=scheme, port=port)
            await server.start_server(
                ssl=cert.server_context(tls_dir) if scheme == "https" else None)
            jar = CookieJar(unsafe=True)
            try:
                async with ClientSession(connector=TCPConnector(ssl=False), cookie_jar=jar) as http:
                    return await fn(http, f"{scheme}://{HOST}:{server.port}")
            finally:
                await server.close()
        return asyncio.run(main())
    return run


def lan_is_tls(run):
    async def go(http, url):
        return url.startswith("https")
    return run(go)


async def sign_in(http, url, given=PASSWORD):
    return await http.post(f"{url}/login", data={"password": given}, allow_redirects=False)


def test_nothing_is_readable_before_signing_in(lan):
    async def go(http, url):
        statuses = {}
        for path in ("/api/queue", "/api/history", "/api/metrics", "/api/events", "/healthz",
                     "/api/jobs/x", "/api/jobs/x/log.txt", "/static/app.js"):
            reply = await http.get(url + path, allow_redirects=False)
            statuses[path] = reply.status
        page = await http.get(f"{url}/", allow_redirects=False)
        return statuses, page.status, page.headers["Location"]
    statuses, status, location = lan(go)
    assert status == 303 and location == "/login"
    assert statuses.pop("/static/app.js") == 303
    assert set(statuses.values()) == {401}


def test_sign_in_sets_a_locked_down_cookie_and_opens_the_api(lan):
    async def go(http, url):
        reply = await sign_in(http, url)
        queue = await http.get(f"{url}/api/queue")
        health = await (await http.get(f"{url}/healthz")).json()
        return reply.status, reply.headers["Set-Cookie"], queue.status, health
    status, cookie, queue, health = lan(go)
    assert status == 303 and queue == 200 and health["lan"] is True
    assert cookie.startswith(f"{COOKIE}=")
    for flag in ("HttpOnly", "SameSite=Strict", "Path=/"):
        assert flag in cookie
    assert ("Secure" in cookie) is lan_is_tls(lan)


def test_wrong_password_does_not_sign_in(lan):
    async def go(http, url):
        reply = await sign_in(http, url, "wrong")
        return reply.status, await reply.text(), (await http.get(f"{url}/api/queue")).status
    status, text, queue = lan(go)
    assert status == 401 and "Wrong password" in text and queue == 401


def test_repeated_failures_lock_even_the_right_password(lan):
    async def go(http, url):
        for _ in range(FREE_FAILURES + 1):
            await sign_in(http, url, "wrong")
        reply = await sign_in(http, url)
        return reply.status, await reply.text()
    status, text = lan(go)
    assert status == 429 and "Try again" in text


def test_sign_out_ends_the_session_on_the_server(lan):
    async def go(http, url):
        await sign_in(http, url)
        token = http.cookie_jar.filter_cookies(URL(url))[COOKIE].value
        out = await http.post(f"{url}/logout")
        replay = await http.get(f"{url}/api/queue", headers={"Cookie": f"{COOKIE}={token}"})
        return out.status, replay.status
    assert lan(go) == (204, 401)


def test_outside_the_range_is_refused_even_with_the_login_page(lan):
    async def go(http, url):
        page = await http.get(f"{url}/login")
        post = await sign_in(http, url)
        return page.status, post.status
    assert lan(go, range_="10.0.0.0/8") == (403, 403)


def test_wrong_host_is_refused_on_the_lan_listener(lan):
    async def go(http, url):
        reply = await http.get(f"{url}/login", headers={"Host": "evil.example"})
        return reply.status
    assert lan(go) == 421


def test_cross_site_post_is_refused_but_a_same_site_null_origin_passes(lan):
    # Over HTTP browsers omit this header; a browser that sends it is still held to it.
    async def go(http, url):
        cross = await http.post(f"{url}/login", data={"password": PASSWORD},
                                headers={"Sec-Fetch-Site": "cross-site"}, allow_redirects=False)
        same = await http.post(f"{url}/login", data={"password": PASSWORD},
                               headers={"Sec-Fetch-Site": "same-origin", "Origin": "null"},
                               allow_redirects=False)
        return cross.status, same.status
    assert lan(go) == (403, 303)


def test_login_page_allows_only_its_own_form_and_uses_no_inline_code(lan):
    async def go(http, url):
        page = await http.get(f"{url}/login")
        style = await http.get(f"{url}/static/style.css")
        return page.status, page.headers, await page.text(), style.status
    status, headers, text, style = lan(go)
    assert status == 200 and style == 200
    assert headers["Content-Security-Policy"] == LOGIN_CSP
    assert "<script" not in text and "style=" not in text
    assert headers["Cache-Control"] == "no-store"


def test_signed_in_visitor_skips_the_login_page(lan):
    async def go(http, url):
        await sign_in(http, url)
        reply = await http.get(f"{url}/login", allow_redirects=False)
        return reply.status
    assert lan(go) == 303


def test_without_a_password_the_page_opens_directly_and_sign_in_is_gone(lan):
    async def go(http, url):
        statuses = [(await http.get(url + p, allow_redirects=False)).status
                    for p in ("/", "/api/queue", "/api/machines", "/static/style.css")]
        login = await http.get(f"{url}/login", allow_redirects=False)
        health = await (await http.get(f"{url}/healthz")).json()
        posted = await http.post(f"{url}/login", data={"password": "x"})
        return statuses, login.status, health, posted.status
    statuses, login, health, posted = lan(go, open_lan=True)
    assert set(statuses) == {200} and login == 303 and posted == 404
    assert health["lan"] is True and health["sign_in"] is False


def test_without_a_password_the_range_and_host_rules_still_hold(lan):
    async def go(http, url):
        return (await http.get(f"{url}/api/queue")).status
    assert lan(go, range_="10.0.0.0/8", open_lan=True) == 403

    async def wrong_host(http, url):
        return (await http.get(f"{url}/", headers={"Host": "evil.example"})).status
    assert lan(wrong_host, open_lan=True) == 421


def test_tunnel_listener_has_no_sign_in_and_stays_open(call):
    async def go(client):
        health = await (await client.get("/healthz")).json()
        return (await client.get("/login")).status, (await client.get("/api/queue")).status, health
    login_status, queue, health = call(go)
    assert login_status == 404 and queue == 200 and health["lan"] is False


def test_tunnel_listener_with_lan_on_keeps_the_local_host_rule(data, hub):
    access = LanAccess(ipaddress.ip_network("192.168.1.0/24"), frozenset({"192.168.1.50"}),
                       ("192.168.1.50", 8443), "", Sessions(lambda: NOW),
                       LoginLimiter(lambda: NOW))

    async def main():
        app = build_app(data, hub, clock=lambda: NOW, start_hub=False, lan=access)
        async with TestClient(TestServer(app)) as client:
            good = await client.get("/api/queue")
            bad = await client.get("/api/queue", headers={"Host": "192.168.1.50:8090"})
            login = await client.post("/login", data={"password": "x"})
            return good.status, bad.status, login.status
    assert asyncio.run(main()) == (200, 421, 404)
