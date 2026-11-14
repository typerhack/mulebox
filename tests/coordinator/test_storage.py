"""What mulebox holds on each node and the keep marks, on the coordinator (coordinator/storage.py)."""

from mulebox.common.branch_folder import slug
from mulebox.common.protocol import MessageType
from mulebox.coordinator import api, storage

from .helpers import claimed, queued, request

REPORT = {"at": 5.0, "disk": {"total": 490, "free": 55, "reserve": 49},
          "projects": [{"project": "example-app", "folders": [
              {"folder": slug("feature/a"), "size": 700, "fate": "stays"}]}]}


def claim(store, staging, worker="build-1", now=1.0, **extra):
    body = {"worker": worker, "capabilities": ["node"], "free_slots": 1,
            "settings": {"slots": 1, "priority": "normal"}, **extra}
    return api.handle(store, staging, request("claim", **body), now, cluster_slots=1)


def test_a_report_with_a_claim_is_kept_and_read_back_with_branch_names(store, staging):
    queued(store, staging, now=0.5, branch="feature/a")  # the history names the branch
    claim(store, staging, storage=REPORT)
    reply = api.handle(store, staging, request("storage"), 2.0)
    assert reply.type is MessageType.STORAGE_OK
    node = reply.body["nodes"][0]
    assert node["node"] == "build-1" and node["online"] and node["report"] == REPORT
    assert reply.body["branches"]["example-app"][slug("feature/a")] == "feature/a"


def test_a_bad_or_huge_report_is_dropped_and_the_claim_still_works(store, staging, monkeypatch):
    assert claim(store, staging, storage={"no": "time"}).type is not MessageType.ERROR
    monkeypatch.setattr(storage, "MAX_REPORT", 10)
    claim(store, staging, storage=REPORT, now=2.0)
    nodes = api.handle(store, staging, request("storage"), 3.0).body["nodes"]
    assert nodes[0]["report"] is None


def test_keep_marks_reach_every_claim_and_can_be_dropped(store, staging):
    assert claim(store, staging).body["storage_keeps"] == []
    reply = api.handle(store, staging, request("storage_keep", project="example-app",
                                               branch="main"), 2.0)
    assert reply.type is MessageType.STORAGE_KEEP_OK
    api.handle(store, staging, request("storage_keep", project="clinic"), 2.0)
    assert claim(store, staging, now=3.0).body["storage_keeps"] == [
        {"project": "clinic", "branch": None}, {"project": "example-app", "branch": "main"}]
    api.handle(store, staging, request("storage_keep", project="example-app", branch="main",
                                       keep=False), 4.0)
    marks = api.handle(store, staging, request("storage"), 5.0).body["keeps"]
    assert [(m["project"], m["branch"]) for m in marks] == [("clinic", None)]


def test_a_heartbeat_carries_the_report_and_the_marks(store, staging):
    job = claimed(store, staging, now=1.0)
    api.handle(store, staging, request("storage_keep", project="example-app"), 2.0)
    reply = api.handle(store, staging, request("heartbeat", job_id=job["job_id"],
                                               attempt_id=job["attempt_id"], lease="worker",
                                               storage=REPORT), 3.0)
    assert reply.body["storage_keeps"] == [{"project": "example-app", "branch": None}]
    nodes = api.handle(store, staging, request("storage"), 4.0).body["nodes"]
    assert nodes[0]["report"] == REPORT
