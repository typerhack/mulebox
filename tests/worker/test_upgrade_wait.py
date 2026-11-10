"""The machine's side of a queued upgrade (worker/upgrade_wait.py)."""

import argparse
import subprocess

from mulebox.common.protocol import Message, MessageType
from mulebox.worker import upgrade_wait


class FakeLink:
    def __init__(self, turns):
        self.turns = list(turns)
        self.sent = []

    def call(self, msg):
        self.sent.append(msg.body)
        return Message(MessageType.STATUS_OK, "r", {"job_id": "j", "state": "queued", **self.turns.pop(0)})


def bundle_in(tmp_path):
    folder = tmp_path / "staging" / "upgrades" / "upgrade-1"
    folder.mkdir(parents=True)
    (folder / "install.sh").write_text("echo installed\n")
    (folder / "mulebox-9.9.9-py3-none-any.whl").write_bytes(b"")
    return folder


def run_wait(monkeypatch, tmp_path, turns, install_code=0):
    folder = bundle_in(tmp_path)
    link = FakeLink(turns)
    removed, ran = [], []

    class Paths:
        roots = object()

    monkeypatch.setattr(upgrade_wait, "_open", lambda: (None, link, Paths))
    monkeypatch.setattr(upgrade_wait.time, "sleep", lambda s: None)
    monkeypatch.setattr(upgrade_wait.safepath, "remove_tree", lambda p, r: removed.append(p))

    def fake_run(argv, **kw):
        ran.append(argv)
        return subprocess.CompletedProcess(argv, install_code if argv[0] == "bash" else 0)

    monkeypatch.setattr(upgrade_wait.subprocess, "run", fake_run)
    args = argparse.Namespace(job_id="job-01M70000000000000000000000", bundle=str(folder))
    return upgrade_wait._wait(args), link, ran, removed, folder


def test_it_waits_for_its_turn_installs_and_reports(monkeypatch, tmp_path):
    code, link, ran, removed, folder = run_wait(
        monkeypatch, tmp_path, [{"go": False}, {"go": False}, {"go": True}])
    assert code == 0 and len(link.sent) == 3
    assert ran[0][:2] == ["bash", str(folder / "install.sh")]
    assert ran[1][1:3] == ["upgrade-report", "job-01M70000000000000000000000"]
    assert "--passed" in ran[1] and removed == [folder]


def test_a_failed_install_is_reported_failed(monkeypatch, tmp_path):
    code, _, ran, _, _ = run_wait(monkeypatch, tmp_path, [{"go": True}], install_code=3)
    assert code == 1 and "--failed" in ran[1]


def test_a_cancelled_upgrade_leaves_nothing(monkeypatch, tmp_path):
    code, _, ran, removed, folder = run_wait(
        monkeypatch, tmp_path, [{"go": False}, {"go": False, "outcome": "cancelled"}])
    assert code == 0 and ran == [] and removed == [folder]
