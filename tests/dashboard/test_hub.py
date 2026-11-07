import asyncio

from .conftest import NOW


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
