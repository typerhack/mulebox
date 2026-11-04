"""`mulebox projects`: worked out from the jobs, with no table of its own."""

from mulebox.coordinator import api

from .helpers import queued, request

NOW = 1000.0


def listing(store, staging):
    return api.handle(store, staging, request("projects"), NOW).body["projects"]


def test_empty_coordinator(store, staging):
    assert listing(store, staging) == []


def test_each_project_once_with_its_count_and_newest_first(store, staging):
    queued(store, staging, NOW, project="one")
    queued(store, staging, NOW + 1, project="one")
    queued(store, staging, NOW + 2, project="two")
    rows = listing(store, staging)
    assert [(r["project"], r["jobs"]) for r in rows] == [("two", 1), ("one", 2)]
    assert rows[0]["last_run"] == NOW + 2


def test_last_result_is_the_newest_job_not_the_first(store, staging):
    first = queued(store, staging, NOW, project="one")
    reply = api.handle(store, staging, request("claim", worker="w", capabilities=[],
                                               free_slots=1), NOW)
    ids = {"job_id": first, "attempt_id": reply.body["attempt_id"]}
    api.handle(store, staging, request("job_update", state="running", **ids), NOW)
    api.handle(store, staging, request("result", outcome="failed", exit_code=1, duration_s=1.0,
                                       **ids), NOW)
    queued(store, staging, NOW + 5, project="one")
    row = listing(store, staging)[0]
    assert row["state"] == "queued" and row["outcome"] is None


def test_old_projects_are_not_lost_to_the_queue_limit(store, staging):
    queued(store, staging, NOW, project="old")
    for offset in range(1, 30):
        queued(store, staging, NOW + offset, project="busy")
    assert {r["project"] for r in listing(store, staging)} == {"old", "busy"}
