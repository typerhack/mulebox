"""Dashboard fixtures: the coordinator's real store and staging, plus a running job."""

import asyncio
import ipaddress

import pytest
from aiohttp import ClientSession, CookieJar
from aiohttp.test_utils import TestClient, TestServer, unused_port

from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import api
from mulebox.dashboard import password
from mulebox.coordinator.store import Store
from mulebox.dashboard.data import DashboardData
from mulebox.dashboard.events import EventBus
from mulebox.dashboard.hub import Hub
from mulebox.dashboard.server import build_app
from mulebox.dashboard.session import LanAccess, LoginLimiter, Sessions
from tests.coordinator.conftest import root_map, staging, store  # noqa: F401
from tests.coordinator.helpers import queued, request

NOW = 1000.0
LOGIN_PAGE = ('<!doctype html><title>sign in</title><link rel="stylesheet" href="/app/login.css">'
              '<!--message--><form method="post" action="/login"></form>')


def fake_app(folder):
    """A stand-in for the front end's build (web/, git-ignored): the page, the sign-in page,
    its stylesheet and a font, which the tests need whether or not anyone ran npm."""
    for name, text in (("index.html", "<!doctype html><title>react</title>"),
                       ("login.html", LOGIN_PAGE), ("login.css", "body{}"),
                       ("fonts/geist.woff2", "font"), ("assets/index-abc.js", "export {};")):
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    return folder


class FakeSampler:
    def fast(self):
        return {"cpu": [10.0, 20.0], "memory": {"total": 100, "available": 60, "used": 40},
                "self": {"cpu": 0.5, "rss": 1024}}


async def no_docker():
    return None


@pytest.fixture
def run_job(store, staging):  # noqa: F811
    """Queue, claim and start a job; returns (job_id, attempt state for later calls)."""
    def run(now=NOW, **extra):
        job_id = queued(store, staging, now, **extra)
        reply = api.handle(store, staging, request(
            "claim", worker="wrk-a", capabilities=[], free_slots=1), now)
        state = {"job_id": job_id, "attempt_id": reply.body["attempt_id"]}
        api.handle(store, staging, request("job_update", state="running", **state), now)
        return job_id, state
    return run


@pytest.fixture
def finish_job(store, staging):  # noqa: F811
    def finish(state, outcome="passed", exit_code=0, now=NOW + 5):
        reply = api.handle(store, staging, request(
            "result", outcome=outcome, exit_code=exit_code, duration_s=5.0, **state), now)
        assert "error" not in reply.body, reply.body
    return finish


@pytest.fixture
def write_log(store, staging):  # noqa: F811
    def write(state, text, offset=0):
        api.handle(store, staging, request("log_chunk", offset=offset, data=text, **state), NOW)
    return write


@pytest.fixture
def data(store, staging):  # noqa: F811
    return DashboardData(store, staging)


@pytest.fixture
def hub(data, root_map):  # noqa: F811
    return Hub(data, EventBus(epoch="test"), root_map, sampler=FakeSampler(),
               docker_list=no_docker, docker_disk=no_docker,
               job_memory=lambda ids, runners: None, clock=lambda: NOW)


@pytest.fixture
def call(data, hub, tmp_path):
    """Run `async fn(client)` against the real app, with the sampling loops off."""
    built = fake_app(tmp_path / "app")

    def run(fn):
        async def main():
            app = build_app(data, hub, clock=lambda: NOW, start_hub=False, app_dir=built)
            async with TestClient(TestServer(app)) as client:
                return await fn(client)
        return asyncio.run(main())
    return run


@pytest.fixture
def readonly_store(staging):  # noqa: F811
    with Store(staging.db_path, readonly=True).open() as opened:
        yield opened


PASSWORD = "correct horse"
HOST = "127.0.0.1"


class FakeCanceller:
    """The dashboard's way to the coordinator, writing down what it was asked."""

    def __init__(self, failure=None):
        self.asked, self.failure = [], failure

    def _answer(self, asked, kind, body):
        self.asked.append(asked)
        if self.failure:
            raise self.failure
        return Message(kind, "req-1", body)

    async def cancel(self, job_id):
        return self._answer(job_id, MessageType.STATUS_OK,
                            {"job_id": job_id, "state": "running", "cancel_requested": True})

    async def control(self, job_id, action):
        return self._answer((job_id, action), MessageType.STATUS_OK,
                            {"job_id": job_id, "state": "queued", "paused": action == "pause"})

    async def machine(self, worker, action):
        return self._answer((worker, action), MessageType.MACHINE_OK,
                            {"worker": worker, "action": action, "running": []})

    async def node_settings(self, worker, **change):
        return self._answer((worker, change), MessageType.NODE_SETTINGS_OK,
                            {"worker": worker, "current": {"slots": 2, "priority": "normal"},
                             "pending": {k: v for k, v in change.items() if k != "cancel"} or None,
                             "suggested": None})

    async def queue_rules(self, body):
        return self._answer(body, MessageType.QUEUE_RULES_OK, {"rules": body.get("rules", {})})


@pytest.fixture(scope="module")
def stored_password(tmp_path_factory):
    directory = tmp_path_factory.mktemp("lan")
    password.save(directory, PASSWORD)
    return directory


@pytest.fixture
def lan(data, hub, stored_password, tmp_path):
    """Run `async fn(http, url)` on a real LAN listener."""
    def run(fn, canceller, *, with_password=True):
        async def main():
            clock = lambda: NOW  # noqa: E731
            port = unused_port()
            stored = password.load(stored_password) if with_password else None
            access = LanAccess(ipaddress.ip_network("127.0.0.0/8"), frozenset({HOST}), (HOST, port),
                               stored, Sessions(clock), LoginLimiter(clock))
            app = build_app(data, hub, clock=clock, start_hub=False, app_dir=fake_app(tmp_path / "app"),
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
