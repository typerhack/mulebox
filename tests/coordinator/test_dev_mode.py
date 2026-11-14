"""A node in dev mode takes only jobs sent to it by name (common/node_settings.py, queue.py)."""

from mulebox.common.protocol import MessageType
from mulebox.coordinator import api

from .helpers import queued, request, submit_body
from .test_node_choice import claim


def status(store, staging, job_id, now):
    return api.handle(store, staging, request("status", job_id=job_id), now).body


def test_a_dev_node_leaves_every_job_not_sent_to_it(store, staging):
    claim(store, staging, "mac-1", 1.0, dev=True)
    job_id = queued(store, staging, now=10.0)
    assert claim(store, staging, "mac-1", 11.0, dev=True).type is MessageType.CLAIM_NONE
    reason = status(store, staging, job_id, 12.0)["waiting_for"]
    assert "in dev mode (mac-1)" in reason and "--dev off" in reason
    pinned = queued(store, staging, now=13.0, on="mac-1")
    reply = claim(store, staging, "mac-1", 14.0, dev=True)
    assert reply.type is MessageType.CLAIM_OK and reply.body["job_id"] == pinned


def test_no_node_waits_for_a_dev_node(store, staging):
    """A dev node with more room, and one ranked above, do not hold a job back."""
    claim(store, staging, "mac-1", 1.0, slots=4, priority="preferred", dev=True)
    claim(store, staging, "build-1", 1.0, slots=1)
    queued(store, staging, now=10.0)
    assert claim(store, staging, "build-1", 11.0, slots=1).type is MessageType.CLAIM_OK


def test_dev_asked_from_afar_counts_before_the_node_wrote_it(store, staging):
    claim(store, staging, "mac-1", 1.0)
    reply = api.handle(store, staging, request("node_settings", worker="mac-1", dev=True), 2.0)
    assert reply.body["pending"] == {"dev": True}
    queued(store, staging, now=3.0)
    first = claim(store, staging, "mac-1", 4.0)
    assert first.type is MessageType.CLAIM_NONE and first.body["node_settings"] == {"dev": True}
    machines = api.handle(store, staging, request("machines"), 5.0).body["workers"]
    assert machines[0]["dev"] is True


def test_dev_on_a_node_too_old_for_it_is_refused(store, staging):
    body = {"worker": "old-1", "capabilities": ["node"], "free_slots": 1,
            "settings": {"slots": 1, "priority": "normal"}}  # no `dev`: before 1.23
    api.handle(store, staging, request("claim", **body), 1.0)
    assert api.handle(store, staging, request("node_settings", worker="old-1"),
                      2.0).body["current"].get("dev") is None  # not reported
    reply = api.handle(store, staging, request("node_settings", worker="old-1", dev=True), 2.0)
    assert reply.type is MessageType.ERROR and "older than 1.23" in reply.body["message"]


def test_a_linux_job_waits_for_a_linux_node(store, staging):
    """The system of M25.6: a Mac node does not take a Linux project's job."""
    claim(store, staging, "mac-1", 1.0, caps=("node", "macos"))
    claim(store, staging, "build-1", 1.0, free=0, caps=("node", "linux"))
    job_id = queued(store, staging, now=10.0, needs=["node"])  # the coordinator adds linux
    assert claim(store, staging, "mac-1", 11.0, caps=("node", "macos")).type is MessageType.CLAIM_NONE
    reply = claim(store, staging, "build-1", 12.0, caps=("node", "linux"))
    assert reply.type is MessageType.CLAIM_OK and reply.body["job_id"] == job_id


def test_an_old_worker_counts_as_linux_unless_it_offers_xcode(store, staging):
    claim(store, staging, "old-mac", 1.0, caps=("node", "xcode"))
    claim(store, staging, "old-pc", 1.0, free=0)
    queued(store, staging, now=10.0, needs=["node"])
    assert claim(store, staging, "old-mac", 11.0, caps=("node", "xcode")).type is (
        MessageType.CLAIM_NONE)
    assert claim(store, staging, "old-pc", 12.0).type is MessageType.CLAIM_OK


def test_a_linux_job_with_only_mac_nodes_is_refused_with_the_fix(store, staging):
    claim(store, staging, "mac-1", 1.0, caps=("node", "macos"))
    reply = api.handle(store, staging, request(
        "submit", **submit_body(needs=["node"])), 2.0)
    assert reply.type is MessageType.ERROR and "`os: any`" in reply.body["message"]


def test_dev_mode_is_for_other_nodes_not_the_coordinators_own(store, staging):
    from mulebox.coordinator import workers
    workers.save_host(store, "build-1")
    claim(store, staging, "build-1", 1.0)
    reply = api.handle(store, staging, request("node_settings", worker="build-1", dev=True), 2.0)
    assert reply.type is MessageType.ERROR and "for other nodes" in reply.body["message"]


def test_a_job_from_an_older_client_gets_the_system_too(store, staging):
    """It sends no `os`; the coordinator adds `linux`, so a Mac node leaves it."""
    claim(store, staging, "mac-1", 1.0, caps=("node", "macos"))
    claim(store, staging, "build-1", 1.0, free=0, caps=("node", "linux"))
    queued(store, staging, now=10.0, needs=["node"])
    assert claim(store, staging, "mac-1", 11.0, caps=("node", "macos")).type is MessageType.CLAIM_NONE
    assert claim(store, staging, "build-1", 12.0, caps=("node", "linux")).type is MessageType.CLAIM_OK


def test_os_any_lets_a_mac_take_it_and_a_bad_os_is_refused(store, staging):
    claim(store, staging, "mac-1", 1.0, caps=("node", "macos"))
    queued(store, staging, now=10.0, needs=["node"], os="any")
    assert claim(store, staging, "mac-1", 11.0, caps=("node", "macos")).type is MessageType.CLAIM_OK
    reply = api.handle(store, staging, request("submit", **submit_body(os="windows")), 12.0)
    assert reply.type is MessageType.ERROR and "linux, macos, any" in reply.body["message"]
