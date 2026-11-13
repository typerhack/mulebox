"""The order rules on the dashboard (dashboard/order_api.py; M23.3, M24.4)."""

from mulebox.client.remote import CoordinatorError
from mulebox.coordinator import api
from mulebox.dashboard.cancel import TOKEN_HEADER
from tests.coordinator.helpers import queued, request

from .conftest import NOW, FakeCanceller
from .test_controls import ask


def test_the_rules_are_read_from_the_store_with_their_defaults(call, store, staging):
    queued(store, staging, project="example-app")

    async def go(client):
        reply = await client.get("/api/queue/rules")
        return reply.status, await reply.json()

    status, body = call(go)
    assert status == 200 and body["rules"] == body["defaults"]
    assert body["defaults"]["aging_min"] == 30 and body["rules"]["fair_turns"] is False
    assert body["projects"] == ["example-app"]
    assert body["project_activity"] == [{"name": "example-app", "last_run": NOW, "runs_7d": 1}]
    assert body["now"] == NOW
    assert body["levels"] == {"min": -3, "max": 3, "words": {"low": -1, "normal": 0, "high": 1}}


def test_a_project_last_used_long_ago_is_still_listed_with_no_runs_this_week(call, store, staging):
    queued(store, staging, now=NOW - 30 * 86400, project="old-drill")
    queued(store, staging, now=NOW - 3600, project="example-app")

    async def go(client):
        return await (await client.get("/api/queue/rules")).json()

    body = call(go)
    assert body["projects"] == ["example-app", "old-drill"]
    assert body["project_activity"] == [
        {"name": "example-app", "last_run": NOW - 3600, "runs_7d": 1},
        {"name": "old-drill", "last_run": NOW - 30 * 86400, "runs_7d": 0}]


def test_a_change_and_a_reset_go_through_the_coordinator(lan):
    change = {"rules": {"projects": {"example-app": 1}, "fair_turns": True}}
    status, answer, asked = ask(lan, "/api/queue/rules", change)
    assert status == 200 and answer["rules"] == change["rules"]
    assert asked == [{"action": "set", "rules": change["rules"]}]
    status, _, asked = ask(lan, "/api/queue/rules", {"reset": True})
    assert status == 200 and asked == [{"action": "reset"}]


def test_bad_bodies_other_pages_and_refusals(lan):
    assert ask(lan, "/api/queue/rules", {"rules": "all"})[0] == 400
    assert ask(lan, "/api/queue/rules", {"reset": "yes"})[0] == 400
    status, _, asked = ask(lan, "/api/queue/rules", {"reset": True},
                           headers={"Origin": "http://evil.example"})
    assert status == 403 and asked == []
    fake = FakeCanceller(CoordinatorError("the level of x must be low, normal, high", "bad_request"))
    status, text, _ = ask(lan, "/api/queue/rules", {"rules": {"github": 9}}, fake=fake)
    assert status == 409 and "must be low" in text


def test_queue_rows_and_a_jobs_page_say_why_a_job_is_where_it_is(data, store, staging):
    older = queued(store, staging, now=NOW - 2, project="example-app")
    newer = queued(store, staging, now=NOW - 1, project="example-api")
    assert all("place_reason" not in row for row in data.queue_jobs(NOW))  # defaults: nothing
    api.handle(store, staging, request("queue_rules", action="set",
                                       rules={"projects": {"example-api": "high"}}), NOW)
    rows = {row["job_id"]: row for row in data.queue_jobs(NOW)}
    assert rows[newer]["position"] == 1 and rows[older]["position"] == 2
    assert rows[newer]["place_reason"] == "project example-api +1; then by arrival"
    assert data.job(newer, NOW)["order"]["level"] == 1


def test_without_controls_a_change_is_not_offered(call):
    async def go(client):
        reply = await client.post("/api/queue/rules", json={"reset": True},
                                  headers={TOKEN_HEADER: "x"})
        return reply.status

    assert call(go) == 405
