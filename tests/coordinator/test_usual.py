"""The usual length of a project's job, from past stage rows."""

import pytest

from mulebox.coordinator import steps, usual
from mulebox.coordinator import store as st

from .helpers import claimed
from .test_api import call


def run(store, staging, durations, outcome="passed", project="example-app", job="check"):
    """A finished job with one row per (stage, seconds), one after the other."""
    claim = claimed(store, staging, project=project, job=job)
    ids = {"job_id": claim["job_id"], "attempt_id": claim["attempt_id"]}
    at, rows = 100.0, []
    for seq, (stage, seconds) in enumerate(durations):
        rows.append({"seq": seq, "stage": stage, "started_at": at, "finished_at": at + seconds,
                     "exit_code": 0, "bytes_downloaded": None, "failing_line": None})
        at += seconds
    call(store, staging, "steps", steps=rows, **ids)
    call(store, staging, "result", outcome=outcome, exit_code=0, duration_s=1, **ids)
    return claim["job_id"]


def read(store, project="example-app", job="check"):
    with store.read() as conn:
        return usual.usual(conn, project, job)


def test_no_history_gives_nothing(store):
    assert read(store) is None


def test_the_median_of_each_stage_and_of_the_whole_job(store, staging):
    for seconds in (10, 20, 900):
        run(store, staging, [("setup", seconds), ("command", 30)])
    assert read(store) == {"runs": 3, "job_s": 50.0, "stages": {"setup": 20.0, "command": 30.0}}


def test_only_passed_runs_count(store, staging):
    run(store, staging, [("command", 10)])
    for outcome in ("failed", "cancelled", "timed_out", "interrupted"):
        run(store, staging, [("command", 1)], outcome=outcome)
    assert read(store)["runs"] == 1 and read(store)["job_s"] == 10.0


def test_only_failed_runs_give_nothing(store, staging):
    run(store, staging, [("command", 1)], outcome="failed")
    assert read(store) is None


def test_other_jobs_and_projects_do_not_count(store, staging):
    run(store, staging, [("command", 10)])
    run(store, staging, [("command", 99)], job="test")
    run(store, staging, [("command", 99)], project="other-app")
    assert read(store)["job_s"] == 10.0
    assert read(store, job="test")["job_s"] == 99.0


def test_a_stage_in_some_runs_only_counts_where_it_ran(store, staging):
    run(store, staging, [("images", 100), ("command", 10)])
    run(store, staging, [("command", 10)])
    assert read(store)["stages"] == {"images": 100.0, "command": 10.0}


def test_a_stage_twice_in_a_run_counts_as_its_sum(store, staging):
    run(store, staging, [("command", 10), ("command", 5)])
    assert read(store)["stages"] == {"command": 15.0}


def test_only_recent_runs_count(store, staging, monkeypatch):
    monkeypatch.setattr(usual, "RUNS", 2)
    run(store, staging, [("command", 500)])
    run(store, staging, [("command", 10)])
    run(store, staging, [("command", 20)])
    assert read(store)["runs"] == 2 and read(store)["job_s"] == 15.0


def test_an_open_row_is_ignored(store, staging):
    job_id = run(store, staging, [("command", 10)])
    with store.write() as conn:
        steps.save(conn, job_id, [{"seq": 5, "stage": "cleanup", "started_at": 1.0,
                                   "finished_at": None, "exit_code": None,
                                   "bytes_downloaded": None, "failing_line": None}])
    assert read(store)["stages"] == {"command": 10.0}


def test_jobs_from_before_steps_do_not_count(store, staging):
    claimed(store, staging)
    with store.write() as conn:
        conn.execute("UPDATE jobs SET outcome = 'passed', state = 'finished'")
    assert read(store) is None


def test_status_shows_it(store, staging):
    run(store, staging, [("command", 10)])
    job_id = claimed(store, staging)["job_id"]
    body = call(store, staging, "status", job_id=job_id).body
    assert body["usual"] == {"runs": 1, "job_s": 10.0, "stages": {"command": 10.0}}


@pytest.mark.parametrize("name", ["percent", "progress", "eta"])
def test_no_guess_at_progress(store, staging, name):
    run(store, staging, [("command", 10)])
    assert name not in read(store)


def test_the_store_has_the_index_for_this(store):
    with store.read() as conn:
        names = {row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "jobs_project" in names
    assert st.SCHEMA_VERSION == 6
