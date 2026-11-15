"""Agents' requests for more space on the dashboard (dashboard/asks_api.py)."""

from mulebox.common import storage_policy
from mulebox.coordinator import api
from tests.coordinator.helpers import request

from .conftest import NOW
from .test_controls import ask


def test_the_page_reads_requests_history_and_the_option(call, store, staging):
    settings = {"slots": 2, "priority": "normal", "dev": False, **storage_policy.DEFAULTS}
    api.handle(store, staging, request("claim", worker="build-1", capabilities=[], free_slots=1,
                                       settings=settings), NOW - 1)
    api.handle(store, staging, request("asks", action="ask", value="30GB", reason="why"), NOW)

    async def go(client):
        found = await client.get("/api/asks?history=5")
        events = await client.get("/api/machines")
        posted = await client.post("/api/asks", json={"action": "agents", "option": "allow"})
        return await found.json(), await events.json(), posted.status

    body, machines, posted = call(go)
    assert [item["value"] for item in body["asks"]] == ["30GB"]
    assert body["agents"] == "ask" and body["changes"] == [] and body["editable"] is False
    assert [item["node"] for item in machines["asks"]] == ["build-1"] and machines["allowed"] == []
    assert posted == 405  # no controls: only the read


def test_an_answer_goes_through_the_coordinator_with_who_answered(lan):
    status, answer, asked = ask(lan, "/api/asks", {"action": "answer", "approve": True,
                                                  "node": "build-1", "value": "25GB", "x": 1})
    assert status == 200 and answer["change_id"] == "chg-1"
    kind, sent = asked[0]
    assert kind == "asks" and sent["action"] == "answer" and sent["value"] == "25GB"
    assert sent["by"] == "the dashboard, from 127.0.0.1" and "x" not in sent


def test_a_bad_action_and_a_foreign_page_are_refused(lan):
    status, _, asked = ask(lan, "/api/asks", {"action": "ask", "value": "99GB"})
    assert status == 400 and asked == []
    status, _, asked = ask(lan, "/api/asks", {"action": "undo", "change": "chg-1"},
                           headers={"Origin": "http://elsewhere.example"})
    assert status == 403 and asked == []
