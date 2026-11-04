"""Dashboard fixtures: the coordinator's real store and staging, plus a running job."""

import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from mulebox.coordinator import api
from mulebox.coordinator.store import Store
from mulebox.dashboard.data import DashboardData
from mulebox.dashboard.events import EventBus
from mulebox.dashboard.hub import Hub
from mulebox.dashboard.server import build_app
from tests.coordinator.conftest import root_map, staging, store  # noqa: F401
from tests.coordinator.helpers import queued, request

NOW = 1000.0


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
               docker_count=no_docker, clock=lambda: NOW)


@pytest.fixture
def call(data, hub, tmp_path):
    """Run `async fn(client)` against the real app, with the sampling loops off."""
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")

    def run(fn):
        async def main():
            app = build_app(data, hub, clock=lambda: NOW, start_hub=False, static_dir=static)
            async with TestClient(TestServer(app)) as client:
                return await fn(client)
        return asyncio.run(main())
    return run


@pytest.fixture
def readonly_store(staging):  # noqa: F811
    with Store(staging.db_path, readonly=True).open() as opened:
        yield opened
