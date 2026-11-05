"""The cancel button: where it exists, what protects it, and the real way to the coordinator."""

import asyncio
import ipaddress
import logging

import pytest
from aiohttp import ClientSession, CookieJar
from aiohttp.test_utils import TestClient, TestServer, unused_port

from mulebox.client.remote import CoordinatorError
from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import store as st
from mulebox.dashboard import commands, password
from mulebox.dashboard.cancel import TOKEN_HEADER
from mulebox.dashboard.canceller import Canceller, rpc_command
from mulebox.dashboard.server import STATIC_DIR, build_app
from mulebox.dashboard.session import LanAccess, LoginLimiter, Sessions
from tests.coordinator.helpers import queued

from .conftest import NOW

PASSWORD = "correct horse"
HOST = "127.0.0.1"


class FakeCanceller:
    def __init__(self, failure=None):
        self.asked, self.failure = [], failure

    async def cancel(self, job_id):
        self.asked.append(job_id)
        if self.failure:
            raise self.failure
        return Message(MessageType.STATUS_OK, "req-1", {"job_id": job_id, "state": "running",
                                                        "cancel_requested": True})


@pytest.fixture(scope="module")
def stored_password(tmp_path_factory):
    directory = tmp_path_factory.mktemp("lan")
    password.save(directory, PASSWORD)
    return directory


@pytest.fixture
def lan(data, hub, stored_password):
    """Run `async fn(http, url)` on a real LAN listener."""
    def run(fn, canceller, *, with_password=True):
        async def main():
            clock = lambda: NOW  # noqa: E731
            port = unused_port()
            stored = password.load(stored_password) if with_password else None
            access = LanAccess(ipaddress.ip_network("127.0.0.0/8"), frozenset({HOST}), (HOST, port),
                               stored, Sessions(clock), LoginLimiter(clock))
            app = build_app(data, hub, clock=clock, start_hub=False, static_dir=STATIC_DIR,
                            lan=access, canceller=canceller)
            server = TestServer(app, port=port)
            await server.start_server()
            try:
                async with ClientSession(cookie_jar=CookieJar(unsafe=True)) as http:
                    return await fn(http, f"http://{HOST}:{port}")
            finally:
                await server.close()
        return asyncio.run(main())
    return run


async def sign_in(http, url):
    await http.post(f"{url}/login", data={"password": PASSWORD}, allow_redirects=False)
    reply = await http.get(f"{url}/api/session")
    return (await reply.json())["cancel_token"]


def page_headers(url, token):
    return {"Origin": url, TOKEN_HEADER: token}


async def post(http, url, job_id, headers):
    return await http.post(f"{url}/api/jobs/{job_id}/cancel", headers=headers)


def test_a_signed_in_page_cancels_and_the_cancel_is_logged(lan, run_job, caplog):
    job_id, _ = run_job(detached=True)
    fake = FakeCanceller()

    async def go(http, url):
        token = await sign_in(http, url)
        reply = await post(http, url, job_id, page_headers(url, token))
        return reply.status, await reply.json(), reply.headers["Cache-Control"]

    with caplog.at_level(logging.INFO, "mulebox.dashboard.cancel"):
        status, body, cache = lan(go, fake)
    assert status == 200 and fake.asked == [job_id] and cache == "no-store"
    assert body == {"job_id": job_id, "state": "running", "outcome": None,
                    "cancel_requested": True}
    assert any(job_id in line and HOST in line for line in caplog.messages)


@pytest.mark.parametrize("change", [
    {"Origin": None},  # no Origin at all
    {"Origin": "null"},  # what a form post sends under no-referrer
    {"Origin": "http://evil.example"},
    {"Origin": "http://127.0.0.1:1"},  # same site, another port: SameSite does not stop this
    {"Origin": "https://127.0.0.1"},
    {TOKEN_HEADER: None},
    {TOKEN_HEADER: "wrong"},
    {TOKEN_HEADER: "wröng"},  # not ASCII: refused, not a crash
    {"Sec-Fetch-Site": "cross-site"},
    {"Sec-Fetch-Site": "same-site"},
])
def test_anything_but_this_dashboards_own_page_is_refused(lan, run_job, change):
    job_id, _ = run_job()
    fake = FakeCanceller()

    async def go(http, url):
        token = await sign_in(http, url)
        origin = change.get("Origin", url)
        headers = {**page_headers(url, token), "Origin": origin, **{
            name: value for name, value in change.items() if name != "Origin"}}
        headers = {name: value for name, value in headers.items() if value is not None}
        return (await post(http, url, job_id, headers)).status

    assert lan(go, fake) == 403
    assert fake.asked == []


def test_a_session_token_does_not_work_without_its_session(lan, run_job):
    job_id, _ = run_job()
    fake = FakeCanceller()

    async def go(http, url):
        token = await sign_in(http, url)
        http.cookie_jar.clear()
        return (await post(http, url, job_id, page_headers(url, token))).status

    assert lan(go, fake) == 401
    assert fake.asked == []


def test_a_preflight_gets_no_approval(lan, run_job):
    job_id, _ = run_job()

    async def go(http, url):
        await sign_in(http, url)
        reply = await http.options(f"{url}/api/jobs/{job_id}/cancel", headers={
            "Origin": "http://evil.example", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": TOKEN_HEADER})
        return reply.status, reply.headers

    status, headers = lan(go, FakeCanceller())
    assert status == 405 and "Access-Control-Allow-Origin" not in headers


def test_no_button_on_the_lan_address_without_a_password(lan, run_job):
    job_id, _ = run_job()
    fake = FakeCanceller()

    async def go(http, url):
        session = await (await http.get(f"{url}/api/session")).json()
        reply = await post(http, url, job_id, {"Origin": url, TOKEN_HEADER: "x"})
        return session, reply.status

    assert lan(go, fake, with_password=False) == ({"cancel_token": None}, 404)
    assert fake.asked == []


def test_no_button_on_the_tunnel_listener(data, hub, run_job, tmp_path):
    """The LAN state exists, the request comes in on the other socket."""
    job_id, _ = run_job()
    fake = FakeCanceller()

    async def main():
        clock = lambda: NOW  # noqa: E731
        access = LanAccess(ipaddress.ip_network("127.0.0.0/8"), frozenset({HOST}),
                           ("192.168.1.50", 8090), "hash", Sessions(clock), LoginLimiter(clock))
        app = build_app(data, hub, clock=clock, start_hub=False, static_dir=STATIC_DIR, lan=access,
                        canceller=fake)
        async with TestClient(TestServer(app)) as client:
            client.session.headers["Host"] = HOST
            session = await (await client.get("/api/session")).json()
            reply = await client.post(f"/api/jobs/{job_id}/cancel")
            return session, reply.status

    assert asyncio.run(main()) == ({"cancel_token": None}, 404)
    assert fake.asked == []


def test_without_the_setting_there_is_no_route_at_all(call, run_job):
    job_id, _ = run_job()

    async def go(client):
        session = await (await client.get("/api/session")).json()
        return session, (await client.post(f"/api/jobs/{job_id}/cancel")).status

    assert call(go) == ({"cancel_token": None}, 404)


@pytest.mark.parametrize("settings, has_password, expected", [
    ({}, True, False),
    ({"cancel_button": False}, True, False),
    ({"cancel_button": True}, True, True),
    ({"cancel_button": True}, False, False),
])
def test_the_setting_counts_only_with_a_password(settings, has_password, expected):
    node = type("Node", (), {"dashboard": settings})
    access = type("Access", (), {"password_hash": "hash" if has_password else None})
    assert (commands._canceller(node, access, None) is not None) is expected


def test_the_setting_alone_does_nothing_in_local_mode():
    node = type("Node", (), {"dashboard": {"cancel_button": True}})
    assert commands._canceller(node, None, None) is None


def test_a_finished_job_and_a_reservation_are_refused(lan, run_job, finish_job, store):
    done, state = run_job()
    finish_job(state)
    reservation, _ = run_job()
    with store.write() as conn:
        st.update_job(conn, reservation, kind="runner")
    fake = FakeCanceller()

    async def go(http, url):
        token = await sign_in(http, url)
        replies = [await post(http, url, job_id, page_headers(url, token))
                   for job_id in (done, reservation, "job-nosuch")]
        return [reply.status for reply in replies]

    assert lan(go, fake) == [409, 409, 404]
    assert fake.asked == []


def test_a_coordinator_failure_is_said_and_the_job_stays(lan, run_job):
    job_id, _ = run_job()
    fake = FakeCanceller(CoordinatorError("the coordinator did not answer in time", "timeout"))

    async def go(http, url):
        reply = await post(http, url, job_id, page_headers(url, await sign_in(http, url)))
        return reply.status, await reply.text()

    status, text = lan(go, fake)
    assert status == 502 and "did not answer" in text


def rpc(node_file, root_map):
    roots = "".join(f'{name} = "{path}"\n' for name, path in root_map.items())
    node_file.write_text(f'name = "build-1"\nroles = ["coordinator", "worker"]\n[roots]\n{roots}',
                         encoding="utf-8")
    return Canceller(node_file)


def test_the_real_mulebox_rpc_cancels_a_queued_and_a_running_job(
        store, staging, root_map, run_job, tmp_path):  # noqa: F811
    canceller = rpc(tmp_path / "node.toml", root_map)
    running, _ = run_job()
    waiting = queued(store, staging, NOW)

    first = asyncio.run(canceller.cancel(waiting))
    assert first.body["state"] == "finished" and first.body["outcome"] == "cancelled"
    second = asyncio.run(canceller.cancel(running))
    assert second.body["state"] == "running" and second.body["cancel_requested"] is True
    again = asyncio.run(canceller.cancel(running))  # a retry after a lost reply changes nothing
    assert again.body["cancel_requested"] is True
    with store.read() as conn:
        assert st.require_job(conn, running)["cancel_requested"] is True


def test_the_real_mulebox_rpc_says_when_a_job_is_unknown(root_map, store, tmp_path):  # noqa: F811
    canceller = rpc(tmp_path / "node.toml", root_map)
    with pytest.raises(CoordinatorError) as caught:
        asyncio.run(canceller.cancel("job-" + "0" * 12))
    assert caught.value.code in ("not_found", "bad_request")


def test_a_command_that_says_nothing_and_one_that_hangs(tmp_path):
    silent = Canceller(command=("/bin/sh", "-c", "exit 2"))
    with pytest.raises(CoordinatorError, match="no reply"):
        asyncio.run(silent.cancel("job-x"))
    hanging = Canceller(command=("/bin/sleep", "30"), timeout_s=0.05)
    with pytest.raises(CoordinatorError, match="in time") as caught:
        asyncio.run(hanging.cancel("job-x"))
    assert caught.value.code == "timeout"


def test_the_command_is_this_python_with_the_given_config(tmp_path):
    command = rpc_command(tmp_path / "node.toml")
    assert command[1:4] == ("-m", "mulebox.cli", "rpc") and command[-1].endswith("node.toml")
    assert "--node-config" not in rpc_command(None)
