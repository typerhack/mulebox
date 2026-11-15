"""`mulebox storage`, `mulebox project keep` and the storage flags of `mulebox machine config`,
against the real coordinator code (client/storage_commands.py, client/machine_config.py)."""

import json
import time

import pytest

from mulebox.cli import build_parser
from mulebox.client import machine_config, storage_commands
from mulebox.common import storage_policy
from mulebox.common.branch_folder import slug
from mulebox.coordinator import api
from tests.client.test_machine_config import StoreRemote
from tests.coordinator.conftest import root_map, staging, store  # noqa: F401
from tests.coordinator.helpers import queued, request

GB = 10**9
NOW = time.time()
REPORT = {
    "at": NOW - 120, "disk": {"total": 490 * GB, "free": 55 * GB, "reserve": 49 * GB},
    "policy": storage_policy.DEFAULTS,
    "projects": [{"project": "example-app", "home": GB // 10, "caches": 2 * GB, "folders": [
        {"folder": slug("main"), "size": 700_000_000, "last_used": NOW - 3600, "fate": "latest"},
        {"folder": slug("feature/a"), "size": 600_000_000, "last_used": NOW - 3 * 86400,
         "fate": "stays", "removed_in": 4.0}]}],
    "shared": {"toolchains": GB, "runners": 4 * GB, "staging": 0},
    "docker": {"images": {"size": 9 * GB, "reclaimable": 7 * GB, "count": 99}},
    "idle": [{"project": "old-app", "days": 20, "size": GB, "kept": False}],
    "short": {"need": 3 * GB, "could_free": 4 * GB,
              "folders": [{"project": "example-app", "folder": slug("feature/a"),
                           "size": 600_000_000, "last_used": NOW, "fate": "stays"}]},
    "removed": {"count": 3, "bytes": 2 * GB}}


@pytest.fixture
def remote(store, staging, monkeypatch):  # noqa: F811
    now = time.time()  # the claim's time, not the module's: online is judged by the real clock
    queued(store, staging, now=now - 10, branch="feature/a")
    body = {"worker": "build-1", "capabilities": [], "free_slots": 2,
            "settings": {"slots": 2, "priority": "normal", "dev": False, **storage_policy.DEFAULTS},
            "storage": {**REPORT, "at": now - 120}}
    api.handle(store, staging, request("claim", **body), now)
    fake = StoreRemote(store, staging)
    monkeypatch.setattr(storage_commands, "connect", lambda: fake)
    monkeypatch.setattr(machine_config, "connect", lambda: fake)
    return fake


def run(*argv):
    args = build_parser().parse_args(list(argv))
    return args.func(args)


def test_storage_says_what_each_node_holds_and_what_goes_when(remote, capsys):
    assert run("storage") == 0
    out = capsys.readouterr().out
    assert "build-1: online, measured 2 min ago" in out
    assert "disk: 435.0 GB used of 490.0 GB, 55.0 GB free, keeping 49.0 GB free" in out
    assert "feature/a: 600.0 MB, last job 3 days ago, goes in 4 days" in out  # the branch's name
    assert "kept: latest" in out
    assert "suggestion: old-app had no job for 20 days" in out
    assert "short of space: 3.0 GB" in out
    assert "`mulebox project reset example-app --branch feature/a --yes`" in out
    assert "last sweep removed 3 folder(s), 2.0 GB" in out
    assert "not only mulebox's" in out


def test_a_node_with_no_report_says_why(store, staging, monkeypatch, capsys):  # noqa: F811
    api.handle(store, staging, request("claim", worker="old-1", capabilities=[], free_slots=1),
               time.time())
    monkeypatch.setattr(storage_commands, "connect", lambda: StoreRemote(store, staging))
    run("storage")
    assert "old-1: online, no report yet" in capsys.readouterr().out


def test_keep_and_drop_a_mark(remote, capsys):
    assert run("project", "keep", "example-app", "--branch", "main") == 0
    assert "example-app main: kept on every node" in capsys.readouterr().out
    run("project", "keep", "example-app", "--branch", "main", "--off")
    out = capsys.readouterr().out
    assert "no longer kept" in out and "kept: nothing" in out


def test_machine_config_sends_and_shows_the_storage_settings(remote, capsys):
    assert run("machine", "config", "build-1", "--keep-free", "20%", "--unused-days", "3",
               "--keep-latest", "off", "--idle-days", "30") == 0
    assert remote.sent[-1] == {"worker": "build-1", "keep_free": "20%", "unused_days": 3,
                               "keep_latest": False, "idle_days": 30}
    out = capsys.readouterr().out
    assert "disk:      keeps 10% free; removes branch folders unused 7 days, keeping" in out
    assert "waiting:" in out and "keep_free 20%" in out


def test_history_says_what_each_cleanup_did(remote, capsys):
    from mulebox.coordinator import api as coordinator_api
    sweep = {"started": NOW - 3600, "trigger": "hourly", "auto": True, "count": 1,
             "bytes": 600_000_000, "free_before": 50 * GB, "free_after": 51 * GB,
             "removed": [{"project": "example-app", "folder": "f", "size": 600_000_000,
                          "why": "gone"}], "docker": {"build_cache": GB, "images": 0}}
    coordinator_api.handle(remote.store, remote.staging, request(
        "claim", worker="build-1", capabilities=[], free_slots=2,
        storage={**REPORT, "at": NOW, "sweep": sweep}), NOW)
    assert run("storage", "--history") == 0
    out = capsys.readouterr().out
    assert "build-1: today, hourly: 1 folder(s), 600.0 MB, docker 1.0 GB" in out
    assert "its branch is on no dev machine" in out
    assert run("storage", "--history", "5", "--json") == 0
    body = json.loads(capsys.readouterr().out)
    assert body["history"][0]["trigger"] == "hourly"


def test_what_goes_now_is_said_with_when_and_how_much():
    gone = {"folder": "a", "size": 2 * GB, "fate": "remove", "why": "gone"}
    report = {**REPORT, "next_sweep": NOW + 30 * 60, "measured_at": NOW - 600,
              "projects": [{**REPORT["projects"][0],
                            "folders": [*REPORT["projects"][0]["folders"], gone, gone]}]}
    lines = storage_commands.node_lines({"node": "build-1", "online": True, "report": report},
                                        {}, NOW)
    assert lines[0] == "build-1: online, measured 10 min ago"  # sizes' time, not the plan's
    assert lines[2] == ("  the cleanup in 30 min removes 2 branch folder(s), 4.0 GB "
                        "(`mulebox storage clean` runs it now)")
    off = {**report, "policy": {**storage_policy.DEFAULTS, "auto_clean": False}}
    assert "a cleanup removes 2 branch folder(s), 4.0 GB (automatic cleanup is off" in \
        storage_commands.node_lines({"node": "build-1", "online": True, "report": off}, {}, NOW)[2]
    assert storage_commands.next_line(REPORT, NOW) is None
    thin = {"folder": "b", "size": GB, "fate": "stays", "removed_in": 5.0, "slim": "due",
            "frees": 900_000_000}
    both = {**report, "projects": [{**report["projects"][0],
                                    "folders": [*report["projects"][0]["folders"], thin]}]}
    assert storage_commands.next_line(both, NOW) == (
        "the cleanup in 30 min removes 2 branch folder(s), 4.0 GB and slims 1, 900.0 MB "
        "(`mulebox storage clean` runs it now)")
    assert storage_commands._fate(thin) == "slims next (900.0 MB), goes in 5 days"
    assert storage_commands._fate({**thin, "slim": "done"}) == "slimmed, goes in 5 days"
