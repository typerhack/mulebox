import asyncio

from mulebox.dashboard.events import EventBus
from mulebox.dashboard.hub import Hub

from .conftest import NOW, FakeSampler


def test_queue_event_only_when_the_queue_changes(hub, run_job, finish_job):
    async def go():
        assert await hub.queue_step() is True  # first look: always publishes
        assert await hub.queue_step() is False
        _, state = run_job()
        assert await hub.queue_step() is True
        assert await hub.queue_step() is False
        finish_job(state)
        assert await hub.queue_step() is True
    asyncio.run(go())
    assert hub.current_queue()["recent"][0]["shown_state"] == "passed"


def test_a_running_jobs_cpu_reaches_its_card_without_a_refresh(hub, run_job, store, staging):
    """A long job beside a quiet queue: its CPU readings must publish, not only state changes."""
    from mulebox.coordinator import api
    from tests.coordinator.helpers import request

    def beat(cpu):
        api.handle(store, staging, request("heartbeat", lease="worker", **state,
                                           activity={"job_cpu_pct": cpu}), NOW)

    async def go():
        assert await hub.queue_step() is True
        beat(3.0)
        assert await hub.queue_step() is True  # first reading
        beat(5.0)
        assert await hub.queue_step() is False  # under one step: no flood
        beat(240.0)
        assert await hub.queue_step() is True  # the job got busy
    _, state = run_job()
    asyncio.run(go())
    running = [j for j in hub.current_queue()["running"]]
    assert running[0]["doing"]["cpu_pct"] == 240.0


def test_metrics_carry_the_newest_slow_values_and_a_bounded_history(hub, root_map):
    async def go():
        await hub.disk_step()
        await hub.docker_step()
        return await hub.metrics_step()
    sample = asyncio.run(go())
    assert sample["t"] == NOW and sample["cpu"] == [10.0, 20.0]
    assert sample["docker"] is None and sample["viewers"] == 0
    assert sorted(sample["disk"][0]["roots"]) == sorted(root_map)
    assert list(hub.history) == [sample]
    assert hub.history.maxlen == 150


def test_a_failing_sample_does_not_end_its_loop(hub):
    calls = []

    async def step():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("disk went away")
        task.cancel()

    async def go():
        global task
        task = asyncio.create_task(hub._every(0, step))
        await asyncio.gather(task, return_exceptions=True)
    asyncio.run(go())
    assert len(calls) == 2


def test_docker_steps_give_the_count_the_jobs_memory_and_the_disk_use(data, tmp_path):
    work = tmp_path / "runners" / "build-1-app" / "_work" / "app"
    listing = [{"Id": "a1", "Labels": {"mulebox.job": "job-x"}},
               {"Id": "b2", "Labels": {"com.docker.compose.project.working_dir": str(work)}},
               {"Id": "c3", "Labels": {}}]
    seen = []

    async def containers():
        return listing

    async def disk():
        return 13_700_000_000

    def memory(ids, runners):
        seen.append((ids, runners))
        return 2048

    hub = Hub(data, EventBus(epoch="test"), {"runners": str(tmp_path / "runners")},
              sampler=FakeSampler(), docker_list=containers, docker_disk=disk,
              job_memory=memory, clock=lambda: NOW)
    hub.bus.publish("queue", {"running": [{"kind": "runner", "runner": "build-1-app"},
                                          {"kind": "job", "runner": None}]})

    async def go():
        await hub.docker_step()
        await hub.docker_disk_step()
        return await hub.metrics_step()
    sample = asyncio.run(go())
    assert seen == [(["a1", "b2"], ["build-1-app"])]
    assert sample["docker"] == 3 and sample["jobs_memory"] == 2048
    assert sample["docker_disk"] == 13_700_000_000


def test_no_docker_is_no_count_and_still_reads_the_job_units(data):
    seen = []

    async def nothing():
        return None

    hub = Hub(data, EventBus(epoch="test"), {}, sampler=FakeSampler(), docker_list=nothing,
              docker_disk=nothing, job_memory=lambda ids, runners: seen.append(ids) or 0,
              clock=lambda: NOW)
    asyncio.run(hub.docker_step())
    assert hub.docker is None and hub.jobs_memory == 0 and seen == [[]]
