"""Agents asking for more space, the owner's answer and the settings history
(coordinator/setting_asks.py, setting_changes.py, asks_api.py)."""

import pytest

from mulebox.common import storage_policy
from mulebox.common.protocol import MessageType
from mulebox.coordinator import api

from .helpers import request

GB = 10**9


def claim(store, staging, worker, now, *, max_size="20GB", held=17 * GB):
    settings = {"slots": 2, "priority": "normal", "dev": False, **storage_policy.DEFAULTS,
                "max_size": max_size}
    body = {"worker": worker, "capabilities": ["node"], "free_slots": 2, "settings": settings,
            "storage": {"at": now, "held": held, "policy": {"max_size": max_size}}}
    return api.handle(store, staging, request("claim", **body), now, cluster_slots=1)


def asks(store, staging, now=10.0, **body):
    reply = api.handle(store, staging, request("asks", **body), now)
    assert reply.type is MessageType.ASKS_OK
    return reply.body


def news(store, staging, now=12.0):
    return api.handle(store, staging, request("queue", limit=0, news_for="example-app"),
                      now).body


def agent_asks(store, staging, now=10.0, value="30GB", **extra):
    return asks(store, staging, now, action="ask", value=value, reason="three images this week",
                project="example-app", client="alice-laptop", job_id="job-01", **extra)


def test_a_request_waits_and_the_agent_is_told_it_waits(store, staging):
    claim(store, staging, "build-1", 1.0)
    body = agent_asks(store, staging)
    assert body["ask"]["state"] == "waiting" and body["ask"]["node"] == "build-1"
    assert [item["value"] for item in body["asks"]] == ["30GB"] and body["agents"] == "ask"
    heavy = news(store, staging)["heavy_nodes"][0]
    assert heavy["asked"] == {"value": "30GB", "at": 10.0}
    reply = claim(store, staging, "build-1", 11.0)  # nothing goes to the node before an answer
    assert "node_settings" not in reply.body


def test_approved_it_reaches_the_node_is_recorded_and_told_once(store, staging):
    claim(store, staging, "build-1", 1.0)
    agent_asks(store, staging)
    agent_asks(store, staging, now=11.0, value="24GB")  # two requests, one answer, the larger
    body = asks(store, staging, 12.0, action="answer", approve=True, by="the dashboard")
    assert body["asks"] == []
    change = body["changes"][0]
    assert (change["old"], change["new"], change["how"]) == ("20GB", "30GB", "approved")
    assert change["by"] == "the dashboard" and len(change["asked"]["asks"]) == 2
    assert change["in_force_at"] is None and change["undoable"]
    assert claim(store, staging, "build-1", 13.0).body["node_settings"] == {"max_size": "30GB"}
    claim(store, staging, "build-1", 14.0, max_size="30GB")
    assert asks(store, staging, 15.0)["changes"][0]["in_force_at"] == 14.0
    told = news(store, staging, 16.0)["space_answers"]
    assert [item["state"] for item in told] == ["approved", "approved"]
    assert news(store, staging, 17.0)["space_answers"] == []


def test_another_value_and_a_decline_with_a_note(store, staging):
    claim(store, staging, "build-1", 1.0)
    agent_asks(store, staging)
    body = asks(store, staging, 12.0, action="answer", approve=True, value="25GB", by="me")
    assert body["changes"][0]["how"] == "approved_other" and body["changes"][0]["new"] == "25GB"
    agent_asks(store, staging, now=20.0, value="40GB")
    body = asks(store, staging, 21.0, action="answer", approve=False, note="clean first", by="me")
    change = body["changes"][0]
    assert (change["how"], change["old"], change["new"]) == ("declined", "25GB", "25GB")
    assert change["asked"]["note"] == "clean first" and not change["undoable"]
    claim(store, staging, "build-1", 22.0, max_size="25GB", held=21 * GB)
    assert news(store, staging, 22.0)["heavy_nodes"][0]["declined"]["note"] == "clean first"


def test_allow_applies_at_once_and_the_option_change_is_recorded(store, staging):
    claim(store, staging, "build-1", 1.0)
    asks(store, staging, 5.0, action="agents", option="allow", by="the dashboard")
    body = agent_asks(store, staging)
    assert body["ask"]["state"] == "applied" and body["asks"] == [] and body["agents"] == "allow"
    hows = [(row["how"], row["by"]) for row in body["changes"]]
    assert hows == [("allowed", None), ("agents", "the dashboard")]
    assert claim(store, staging, "build-1", 13.0).body["node_settings"] == {"max_size": "30GB"}


def test_undo_goes_back_once_and_only_the_latest_change(store, staging):
    claim(store, staging, "build-1", 1.0)
    agent_asks(store, staging)
    first = asks(store, staging, 12.0, action="answer", approve=True, by="me")["change_id"]
    body = asks(store, staging, 13.0, action="undo", change=first, by="me")
    assert body["changes"][0]["how"] == "undo" and body["changes"][0]["new"] == "20GB"
    with pytest.raises(Exception, match="latest change"):
        asks(store, staging, 14.0, action="undo", change=first, by="me")


def test_owner_changes_go_in_the_history(store, staging):
    claim(store, staging, "build-1", 1.0)
    api.handle(store, staging, request("node_settings", worker="build-1", slots=3,
                                       by="the dashboard"), 2.0)
    row = asks(store, staging, 3.0)["changes"][0]
    assert (row["setting"], row["old"], row["new"], row["how"]) == ("slots", 2, 3, "owner")


@pytest.mark.parametrize("body, words", [
    ({"value": "10GB"}, "ask for more"),
    ({"value": "30GB", "reason": ""}, "say why"),
    ({"value": "30GB", "setting": "slots"}, "max_size only"),
    ({"value": "30GB", "node": "nope"}, "no machine"),
])
def test_bad_requests_are_refused(store, staging, body, words):
    claim(store, staging, "build-1", 1.0)
    with pytest.raises(Exception, match=words):
        asks(store, staging, action="ask", **{"reason": "why", **body})


def test_with_several_nodes_it_asks_which_unless_one_is_heavy(store, staging):
    claim(store, staging, "build-1", 1.0)
    claim(store, staging, "build-2", 1.0, held=1 * GB)
    assert agent_asks(store, staging)["ask"]["node"] == "build-1"
    claim(store, staging, "build-2", 2.0)
    with pytest.raises(Exception, match="say which node"):
        agent_asks(store, staging, now=12.0)
