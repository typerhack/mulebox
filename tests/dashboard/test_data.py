import asyncio
import sqlite3

import pytest

from mulebox.coordinator import api, queue, steps
from mulebox.coordinator import store as st
from mulebox.coordinator.store import Store
from mulebox.coordinator.workers import OFFLINE_AFTER_S
from tests.coordinator.helpers import queued, request

from .conftest import NOW


def test_store_opened_read_only_refuses_writes(run_job, readonly_store):
    job_id, _ = run_job()
    with readonly_store.read() as conn:
        assert st.fetch_job(conn, job_id)["state"] == "running"
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        with readonly_store.write() as conn:
            st.update_job(conn, job_id, branch="other")


def test_read_only_store_does_not_create_a_database(tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        Store(tmp_path / "missing.db", readonly=True).open().read().__enter__()


def test_job_detail_redacts_the_setup_line(data, run_job):
    job_id, _ = run_job(setup="DB_PASSWORD=fake123 ./init.sh")
    assert data.job(job_id)["setup"] == "DB_PASSWORD=[redacted] ./init.sh"


def test_job_detail_of_a_job_with_no_setup(data, run_job):
    job_id, _ = run_job()
    assert data.job(job_id)["setup"] is None


def test_queue_snapshot_uses_the_status_model(data, run_job, finish_job):
    _, state = run_job()
    finish_job(state, "failed", 2)
    running, _ = run_job(now=NOW + 10)
    snap = data.queue_snapshot(NOW + 20)
    assert [row["job_id"] for row in snap["running"]] == [running]
    assert snap["running"][0]["elapsed_s"] == 10.0
    assert snap["recent"][0]["shown_state"] == "failed"


def test_waiting_jobs_say_where_they_may_go_and_running_ones_do_not(data, store, staging, run_job):
    """The per-machine view needs `needs`, `can_run_on` and `waiting_for` on waiting agent
    jobs only; a running job has its worker, a runner reservation its pinned worker."""
    running, _ = run_job()  # also makes wrk-a known, with no capabilities
    queue.claim(store, "wrk-b", ["docker", "node"], 1, 1, now=NOW)
    plain = queued(store, staging, NOW + 1)
    docker = queued(store, staging, NOW + 2, needs=["docker"])
    rows = {row["job_id"]: row for row in data.queue_jobs(NOW + 3)}
    assert "can_run_on" not in rows[running] and "needs" not in rows[running]
    assert rows[plain]["can_run_on"] == ["wrk-a", "wrk-b"] and rows[plain]["needs"] == []
    assert "waiting_for" not in rows[plain]
    assert rows[docker]["can_run_on"] == ["wrk-b"] and rows[docker]["position"] == 2
    assert "waiting_for" not in rows[docker]
    later = data.queue_jobs(NOW + OFFLINE_AFTER_S + 10)
    assert "offline: wrk-b" in next(r for r in later if r["job_id"] == docker)["waiting_for"]


def test_a_queued_job_nobody_fits_any_more_has_nowhere_to_go(data, store, staging):
    queue.claim(store, "wrk-a", ["gpu"], 1, 1, now=NOW)
    job_id = queued(store, staging, NOW, needs=["gpu"])
    queue.claim(store, "wrk-a", [], 1, 1, now=NOW + 1)  # the capability went away
    row = data.queue_snapshot(NOW + 2)["queued"][0]
    assert row["job_id"] == job_id and row["can_run_on"] == []
    assert "no build machine offers gpu" in row["waiting_for"]


def test_a_pinned_reservation_carries_its_worker_not_a_placement(data, store, staging):
    reply = api.handle(store, staging, request(
        "reserve", worker="wrk-a", repository="example-org/example-app", job="test",
        run_id="1", run_attempt="1", runner="wrk-a-example-app"), NOW)
    assert "job_id" in reply.body, reply.body
    row = data.queue_snapshot(NOW + 1)["queued"][0]
    assert row["pinned_worker"] == "wrk-a" and row["kind"] == "runner"
    assert "can_run_on" not in row and "needs" not in row


def test_hub_republishes_when_a_capable_machine_goes_quiet(hub, store, staging):
    """A machine going offline changes a waiting job's reason, so the queue event follows."""
    queue.claim(store, "wrk-a", ["docker"], 1, 1, now=NOW)
    queued(store, staging, NOW, needs=["docker"])

    async def go():
        assert await hub.queue_step() is True
        assert await hub.queue_step() is False
        hub.clock = lambda: NOW + OFFLINE_AFTER_S + 1
        assert await hub.queue_step() is True
    asyncio.run(go())
    assert "offline" in hub.current_queue()["queued"][0]["waiting_for"]


def test_detail_redacts_the_command_and_never_returns_env(data, run_job):
    secret = "ghp_" + "a" * 36
    job_id, _ = run_job(argv=["deploy", f"--token={secret}"], env={"API_KEY": "hunter2"})
    detail = data.job(job_id)
    assert secret not in detail["command"]
    text = repr(detail)
    assert "env" not in detail and "hunter2" not in text and "attempt_id" not in text
    assert "lease" not in text


@pytest.mark.parametrize("job_id", ["nope", "../../etc/passwd", "job-" + "0" * 26])
def test_unknown_or_malformed_ids_are_not_found(data, job_id):
    assert data.job(job_id) is None
    assert data.log_chunk(job_id, 0) is None


def test_history_pages_and_filters(data, run_job, finish_job):
    for n in range(3):
        _, state = run_job(now=NOW + n, project="example-app" if n else "other-app")
        finish_job(state, now=NOW + 100 + n)
    first = data.history(limit=2)
    assert [j["finished_at"] for j in first["jobs"]] == [NOW + 102, NOW + 101]
    second = data.history(limit=2, before=first["next_before"])
    assert [j["project"] for j in second["jobs"]] == ["other-app"]
    assert second["next_before"] is None
    assert len(data.history(project="other-app")["jobs"]) == 1


def test_history_limit_is_bounded(data):
    assert data.history(limit=-5)["jobs"] == []


def test_detail_has_the_stages_and_what_earlier_runs_took(data, store, staging, run_job, finish_job):
    rows = [{"seq": 0, "stage": "command", "started_at": 1.0, "finished_at": 31.0, "exit_code": 0}]
    first, ids = run_job()
    with store.write() as conn:
        steps.save(conn, first, [{**rows[0], "bytes_downloaded": None, "failing_line": None}])
    finish_job(ids, "passed", 0)
    assert data.job(first)["steps"][0]["stage"] == "command"
    assert data.job(first)["usual"] is None
    second, _ = run_job()
    assert data.job(second)["usual"]["job_s"] == 30.0 and data.job(second)["steps"] == []


@pytest.mark.parametrize(("outcome", "exit_code", "step", "stage"), [
    ("failed", None, {"exit_code": None, "failing_line": "no such host"}, "images"),  # never ran
    ("failed", 2, {"exit_code": 2, "failing_line": "boom"}, "images"),
    ("cancelled", 143, {"exit_code": 143, "failing_line": None}, None),  # nothing failed there
    ("passed", 0, {"exit_code": 0, "failing_line": None}, None),
])
def test_detail_names_the_stage_a_job_failed_in(data, store, run_job, finish_job, outcome,
                                                exit_code, step, stage):
    job_id, ids = run_job()
    row = {"seq": 0, "stage": "images", "started_at": 1.0, "finished_at": 2.0,
           "bytes_downloaded": None, **step}
    with store.write() as conn:
        steps.save(conn, job_id, [row])
    finish_job(ids, outcome, exit_code)
    assert data.job(job_id)["failed_stage"] == stage
