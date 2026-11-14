"""A machine's settings window on the dashboard (dashboard/node_settings.py)."""

import pytest

from mulebox.client.remote import CoordinatorError
from mulebox.coordinator import api
from tests.coordinator.helpers import request

from .conftest import NOW, FakeCanceller
from .test_controls import ask

GB = 1 << 30


@pytest.fixture
def machine(store, staging):
    body = {"worker": "build-1", "capabilities": ["docker"], "free_slots": 2,
            "settings": {"slots": 2, "priority": "normal", "dev": False},
            "load": {"cores": 8, "memory": {"total": 16 * GB, "available": 8 * GB, "used": 8 * GB}}}
    api.handle(store, staging, request("claim", **body), NOW - 1)
    return "build-1"


def test_the_window_reads_the_values_the_suggestion_and_the_choices(call, machine):
    async def go(client):
        found = await client.get(f"/api/machines/{machine}/settings")
        unknown = await client.get("/api/machines/nobody/settings")
        posted = await client.post(f"/api/machines/{machine}/settings", json={"slots": 3})
        return await found.json(), unknown.status, posted.status

    view, unknown, posted = call(go)
    assert view["current"] == {"slots": 2, "priority": "normal", "dev": False}
    assert view["pending"] is None
    assert view["suggested"]["slots"] == 2 and view["online"] is True
    assert view["choices"]["priority"] == ["preferred", "normal", "fallback"]
    assert view["editable"] is False  # this app has no controls
    assert unknown == 404 and posted == 405


def test_a_change_goes_through_the_coordinator(lan, machine):
    status, answer, asked = ask(lan, f"/api/machines/{machine}/settings",
                                {"slots": 3, "priority": "preferred"})
    assert status == 200 and answer["pending"] == {"slots": 3, "priority": "preferred"}
    assert answer["editable"] is True
    assert asked == [(machine, {"slots": 3, "priority": "preferred"})]
    status, answer, asked = ask(lan, f"/api/machines/{machine}/settings", {"cancel": True})
    assert status == 200 and asked == [(machine, {"cancel": True})]


@pytest.mark.parametrize("body", [{"slots": 0}, {"slots": "3"}, {"priority": "first"},
                                  {"job_env": {"PATH": "/tmp"}}, {}, [3]])
def test_bad_changes_are_400_and_never_sent(lan, machine, body):
    status, _, asked = ask(lan, f"/api/machines/{machine}/settings", body)
    assert status == 400 and asked == []


def test_a_false_cancel_is_no_cancel(lan, machine):
    status, _, asked = ask(lan, f"/api/machines/{machine}/settings", {"slots": 3, "cancel": False})
    assert status == 200 and asked == [(machine, {"slots": 3})]


def test_a_refusal_is_409_and_another_page_is_403(lan, machine):
    fake = FakeCanceller(CoordinatorError("build-1 has not reported its settings", "conflict"))
    status, text, _ = ask(lan, f"/api/machines/{machine}/settings", {"slots": 3}, fake=fake)
    assert status == 409 and "not reported" in text
    status, _, asked = ask(lan, f"/api/machines/{machine}/settings", {"slots": 3},
                           headers={"Origin": "http://evil.example"})
    assert status == 403 and asked == []
