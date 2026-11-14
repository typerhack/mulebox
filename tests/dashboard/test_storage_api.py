"""What mulebox holds on each node, on the dashboard (dashboard/storage_api.py)."""

from mulebox.coordinator import api
from tests.coordinator.helpers import request

from .conftest import NOW
from .test_controls import ask

REPORT = {"at": NOW - 60, "disk": {"total": 490, "free": 55, "reserve": 49}, "projects": []}


def test_the_page_reads_every_nodes_report(call, store, staging):
    api.handle(store, staging, request("claim", worker="build-1", capabilities=[], free_slots=1,
                                       storage=REPORT), NOW - 1)

    async def go(client):
        found = await client.get("/api/storage")
        posted = await client.post("/api/storage/keep", json={"project": "example-app"})
        return await found.json(), posted.status

    body, posted = call(go)
    assert body["nodes"][0]["node"] == "build-1" and body["nodes"][0]["report"] == REPORT
    assert body["keeps"] == [] and body["editable"] is False
    assert posted == 404  # no controls, no route


def test_a_keep_mark_and_a_removal_go_through_the_coordinator(lan):
    status, answer, asked = ask(lan, "/api/storage/keep",
                                {"project": "example-app", "branch": "main", "keep": False})
    assert status == 200 and answer == {"keeps": []}
    assert asked == [("storage_keep", {"project": "example-app", "branch": "main", "keep": False})]
    status, answer, asked = ask(lan, "/api/storage/remove", {"project": "example-app"})
    assert status == 200 and answer["group"] == "grp-1"
    assert asked == [("project_order", {"action": "reset", "project": "example-app", "yes": True})]


def test_bad_bodies_are_400_and_a_foreign_page_is_refused(lan):
    for body in ({}, {"project": 3}, {"project": "a", "branch": 4}, ["a"]):
        status, _, asked = ask(lan, "/api/storage/remove", body)
        assert status == 400 and asked == []
    status, _, asked = ask(lan, "/api/storage/remove", {"project": "a"},
                           headers={"Origin": "http://elsewhere.example"})
    assert status == 403 and asked == []


def test_run_now_sends_a_sweep_order(lan):
    status, answer, asked = ask(lan, "/api/storage/sweep", {"node": "build-1"})
    assert status == 200 and answer["group"] == "grp-1"
    assert asked == [("project_order", {"action": "sweep", "docker": True, "node": "build-1"})]
    status, _, asked = ask(lan, "/api/storage/sweep", {"docker": False})
    assert asked == [("project_order", {"action": "sweep", "docker": False})]
