"""The strip of what is out of step: workers, laptops and their skill, from real submits."""

from mulebox.dashboard import notices
from mulebox.version import get_version
from tests.coordinator.helpers import submit, submit_body
from tests.coordinator.test_api import call

from .conftest import NOW

V = "0.82.0"


def worker(version, seen=NOW):
    return {"worker": "build-1", "version": version, "last_seen": seen}


def client(version=V, skill="current"):
    return {"client": "alice-laptop", "version": version, "skill": skill}


def test_all_in_step_says_nothing():
    assert notices.notices(V, [worker(V)], [client()], NOW) == []


def test_each_kind_with_its_fix():
    found = notices.notices(V, [worker("0.81.0")], [client("0.81.1", "out_of_date"),
                                                    {**client("0.83.0"), "client": "bob-laptop"}],
                            NOW)
    assert [n["kind"] for n in found] == ["worker", "client", "skill", "client"]
    assert [n["level"] for n in found] == ["danger", "warning", "warning", "warning"]
    assert "build-1 runs mulebox 0.81.0, the coordinator 0.82.0" in found[0]["text"]
    assert "pipx upgrade mulebox" in found[1]["fix"]
    assert "mulebox skill update" in found[2]["fix"]
    assert "mulebox setup <host>" in found[3]["fix"]


def test_an_offline_worker_is_left_out():
    assert notices.notices(V, [worker("0.1.0", seen=NOW - 3600)], [], NOW) == []


def test_submits_record_the_laptop_and_reach_the_panel(store, staging, data):
    submit(store, staging, NOW, client="alice-laptop", client_version="0.1.0", skill="out_of_date")
    body = submit_body(client="alice-laptop", client_version=get_version(), skill="current")
    call(store, staging, "submit", now=NOW + 1, **body)
    submit(store, staging, NOW, client="old-laptop")  # an older client says neither: not listed
    panel = data.machines(NOW + 2)
    assert panel["notices"] == []  # its newest word counts
    call(store, staging, "submit", now=NOW + 3,
         **submit_body(client="alice-laptop", client_version="0.1.0", skill="none"))
    assert [n["kind"] for n in data.machines(NOW + 4)["notices"]] == ["client"]


def test_a_bad_skill_state_is_refused(store, staging):
    reply = call(store, staging, "submit", **submit_body(client_version=V, skill="maybe"))
    assert reply.body["code"] == "bad_request"


def test_a_laptop_not_seen_for_weeks_is_left_out(store, staging, data):
    submit(store, staging, NOW, client="alice-laptop", client_version="0.1.0")
    assert data.machines(NOW + 15 * 86400)["notices"] == []
