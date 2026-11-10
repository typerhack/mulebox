"""Paused projects (coordinator/project_pause.py)."""

from mulebox.coordinator import api, queue, reservations

from .helpers import queued, request


def pause(store, staging, *projects, action="pause", now=1000.0, minutes=None):
    body = {"action": action, "projects": list(projects)}
    if minutes:
        body["minutes"] = minutes
    return api.handle(store, staging, request("project_pause", **body), now).body


def claim(store, worker="wrk-a", now=1001.0):
    return queue.claim(store, worker, ["node", "docker"], 2, 10, now=now)


def test_a_paused_projects_jobs_wait_and_others_go_on(store, staging):
    held = queued(store, staging, now=1.0, project="example-app")
    other = queued(store, staging, now=2.0, project="example-drill")
    assert "example-app" in pause(store, staging, "example-app")["paused"]
    reason = api.handle(store, staging, request("status", job_id=held), 1001.0).body["waiting_for"]
    assert "project example-app is paused" in reason
    assert claim(store)["job_id"] == other
    assert claim(store) is None
    pause(store, staging, "example-app", action="resume")
    assert claim(store)["job_id"] == held


def test_a_pause_ends_by_itself(store, staging):
    held = queued(store, staging, now=1.0, project="example-app")
    pause(store, staging, "example-app", minutes=1)
    assert claim(store, now=1030.0) is None
    assert claim(store, now=1061.0)["job_id"] == held
    assert pause(store, staging, action="list", now=1061.0)["paused"] == {}


def test_a_paused_projects_github_runs_wait(store, staging):
    pause(store, staging, "o__example-app")
    with store.write() as conn:
        slot = reservations.create(conn, {
            "pinned_worker": "wrk-a", "project": "o__example-app", "job": "ci", "runner": "r1",
            "idempotency_key": "gh-1"}, 1000.0)
        assert reservations.try_grant(conn, slot, 1001.0, 10)["state"] == "queued"
