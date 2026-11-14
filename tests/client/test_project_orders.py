"""`mulebox project reset|clean` on every node, through the real coordinator code."""

import threading
import time
from types import SimpleNamespace

from mulebox import cli
from mulebox.client import project_commands
from mulebox.client.remote import CoordinatorError
from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import api


def node_answers(local, name, output, stop):
    """A stand-in node: online, and answering each order it is handed with `output`."""
    def claim():
        return api.handle(local.store, local.staging, Message(MessageType.CLAIM, "r", {
            "worker": name, "capabilities": [], "free_slots": 0}), time.time())

    claim()

    def loop():
        while not stop.is_set():
            for order in claim().body.get("orders", []):
                api.handle(local.store, local.staging, Message(MessageType.ORDER_DONE, "r", {
                    "order_id": order["order_id"], "exit_code": 0, "output": output}),
                    time.time())
            time.sleep(0.05)
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def test_reset_prints_every_nodes_answer(local, monkeypatch, capsys):
    monkeypatch.setattr(project_commands, "POLL_S", 0.05)
    stop = threading.Event()
    threads = [node_answers(local, "build-1", "no folder at /home/alice/x", stop),
               node_answers(local, "mac-1", "/Users/alice/x, 12 MB\nnothing removed", stop)]
    try:
        assert cli.main(["project", "reset", "example-app"]) == 0
    finally:
        stop.set()
        for thread in threads:
            thread.join(2)
    out = capsys.readouterr().out
    assert "build-1:\n  no folder at /home/alice/x" in out
    assert "mac-1:\n  /Users/alice/x, 12 MB\n  nothing removed" in out


def test_with_no_node_online_it_says_so(local, capsys):
    assert cli.main(["project", "clean"]) == 1
    assert "no node is online" in capsys.readouterr().err


def test_a_lost_or_failed_node_fails_the_command(capsys):
    group = {"answers": [{"node": "build-1", "lost": True},
                         {"node": "build-2", "exit_code": 2, "output": "mulebox: refused"}]}
    assert project_commands.show(group) == 1
    out = capsys.readouterr().out
    assert "build-1: did not answer" in out and "build-2:\n  mulebox: refused" in out


def test_an_older_coordinator_gets_the_old_path(monkeypatch, capsys):
    calls = []

    class Old:
        def call(self, msg):
            raise CoordinatorError("unknown message type 'project_order'", "bad_request")

        def project_home(self, *argv):
            calls.append(argv)
            return SimpleNamespace(stdout=b"would remove 0 branch folders\n")
    monkeypatch.setattr(project_commands, "connect", lambda: Old())
    assert cli.main(["project", "clean", "--days", "3"]) == 0
    assert calls == [("clean", "--days", "3")]
    captured = capsys.readouterr()
    assert "older than 1.22.0" in captured.err and "would remove 0" in captured.out
