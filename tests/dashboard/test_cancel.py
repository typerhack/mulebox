"""The cancel button: where it exists, what protects it, and the real way to the coordinator.
The `lan` fixture and the fake are in conftest.py, shared with test_controls.py."""

import asyncio
import ipaddress
import logging

import pytest
from aiohttp.test_utils import TestClient, TestServer

from mulebox.client.remote import CoordinatorError
from mulebox.coordinator import store as st
from mulebox.dashboard import commands
from mulebox.dashboard.cancel import TOKEN_HEADER
from mulebox.dashboard.canceller import Canceller, rpc_command
from mulebox.dashboard.server import build_app
from mulebox.dashboard.session import LanAccess, LoginLimiter, Sessions
from mulebox.runners.cancel_run import run_of
from tests.coordinator.helpers import queued

from .conftest import HOST, NOW, PASSWORD, FakeCanceller

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


def test_the_lan_address_without_a_password_has_the_controls(lan, run_job):
    """mulebox is for its owner's own network: no sign-in, still the page's own token."""
    job_id, _ = run_job()
    fake = FakeCanceller()

    async def go(http, url):
        token = (await (await http.get(f"{url}/api/session")).json())["action_token"]
        refused = await post(http, url, job_id, {"Origin": url, TOKEN_HEADER: "x"})
        done = await post(http, url, job_id, page_headers(url, token))
        return refused.status, done.status

    assert lan(go, fake, with_password=False) == (403, 200)
    assert fake.asked == [job_id]


def test_the_tunnel_listener_has_the_controls(data, hub, run_job):
    """The LAN state exists with a password, the request comes in on the tunnel's socket."""
    job_id, _ = run_job()
    fake = FakeCanceller()

    async def main():
        clock = lambda: NOW  # noqa: E731
        access = LanAccess(ipaddress.ip_network("127.0.0.0/8"), frozenset({HOST}),
                           ("192.168.1.50", 8090), "hash", Sessions(clock), LoginLimiter(clock))
        app = build_app(data, hub, clock=clock, start_hub=False, lan=access,
                        canceller=fake)
        async with TestClient(TestServer(app)) as client:
            origin = f"http://{HOST}:{client.server.port}"
            client.session.headers["Host"] = f"{HOST}:{client.server.port}"
            token = (await (await client.get("/api/session")).json())["action_token"]
            bare = await client.post(f"/api/jobs/{job_id}/cancel")
            done = await client.post(f"/api/jobs/{job_id}/cancel",
                                     headers={"Origin": origin, TOKEN_HEADER: token})
            return bare.status, done.status

    assert asyncio.run(main()) == (403, 200)
    assert fake.asked == [job_id]


def test_with_the_controls_off_there_is_no_route_at_all(call, run_job):
    job_id, _ = run_job()

    async def go(client):
        session = await (await client.get("/api/session")).json()
        return session, (await client.post(f"/api/jobs/{job_id}/cancel")).status

    assert call(go) == ({"action_token": None, "cancel_token": None}, 404)


@pytest.mark.parametrize("settings, expected", [
    ({}, True), ({"controls": True}, True), ({"controls": False}, False),
])
def test_the_controls_are_on_unless_turned_off(settings, expected):
    node = type("Node", (), {"dashboard": settings})
    assert (commands._canceller(node, None, None) is not None) is expected


def test_a_finished_job_is_refused_and_a_github_run_goes_to_github(lan, run_job, finish_job,
                                                                     store, monkeypatch):
    done, state = run_job()
    finish_job(state)
    no_address, _ = run_job()
    run, _ = run_job()
    url = "https://github.com/alice/example-app/actions/runs/42"
    with store.write() as conn:
        st.update_job(conn, no_address, kind="runner")
        st.update_job(conn, run, kind="runner", run_url=url)
    asked = []

    def cancel_run(given):  # the real address check, then GitHub's answer without asking it
        asked.append(given)
        run_of(given)
        return "alice/example-app#42"
    monkeypatch.setattr("mulebox.dashboard.cancel.cancel_run", cancel_run)
    fake = FakeCanceller()

    async def go(http, url_):
        token = await sign_in(http, url_)
        replies = [await post(http, url_, job_id, page_headers(url_, token))
                   for job_id in (done, no_address, run, "job-nosuch")]
        return [reply.status for reply in replies]

    assert lan(go, fake) == [409, 502, 200, 404]
    assert fake.asked == [] and asked == [None, url]


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
