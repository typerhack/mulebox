"""Project orders on a node (worker/orders.py): run, report, and no claim while one runs."""

import threading
import time

from mulebox.common.ids import new_id
from mulebox.common.protocol import MessageType
from mulebox.worker import orders
from mulebox.worker import project_home as home

from .conftest import make_tar


def tree(paths, tmp_path, branch):
    tar = tmp_path / "snapshot.tar.gz"
    make_tar(tar, {"README.md": "hello\n"})
    return home.prepare(paths, "example-app", branch, new_id("job"), tar).tree


def test_reset_says_what_would_go_then_removes_it(node, paths, tmp_path):
    tree(paths, tmp_path, "main")
    order = {"action": "reset", "project": "example-app", "yes": False}
    code, output = orders.run(order, node, paths, set())
    assert code == 0 and "nothing removed" in output
    assert paths.project_home("example-app").is_dir()
    code, output = orders.run({**order, "yes": True}, node, paths, set())
    assert code == 0 and "removed" in output and not paths.project_home("example-app").exists()


def test_clean_skips_the_branch_a_job_runs_in(node, paths, tmp_path):
    for branch in ("main", "old", "busy"):
        tree(paths, tmp_path, branch)
    used = {"example-app": {"main": time.time(), "old": 1.0, "busy": 1.0}}
    order = {"action": "clean", "days": 14, "yes": True, "used": used}
    code, output = orders.run(order, node, paths, {("example-app", home.slug("busy"))})
    assert code == 0 and "removed 1 branch folders" in output
    trees = paths.project_home("example-app") / "trees"
    assert not (trees / home.slug("old")).exists() and (trees / home.slug("busy")).is_dir()


def test_an_unknown_order_fails_and_says_so(node, paths):
    code, output = orders.run({"action": "format"}, node, paths, set())
    assert code == 2 and "does not know the order" in output


class Node(orders.Ordering):
    def __init__(self, node, paths):
        self.node, self.paths, self.active, self.sent = node, paths, {}, []

    def _call(self, msg, now):
        self.sent.append(msg)


def test_an_order_is_run_once_and_answered(node, paths, monkeypatch):
    gate = threading.Event()

    def slow(order, *args):
        gate.wait(5)
        return 0, "done"
    monkeypatch.setattr(orders, "run", slow)
    agent = Node(node, paths)
    body = {"orders": [{"order_id": "ord-1", "action": "clean"}]}
    agent._take_orders(body)
    agent._take_orders(body)  # the same order again is not run twice
    assert agent._ordering(1.0) is True and agent.sent == []
    thread = agent._order_state()["running"]["ord-1"]
    gate.set()
    thread.join(5)
    assert agent._ordering(2.0) is False
    assert [(m.type, m.body["order_id"], m.body["output"]) for m in agent.sent] == [
        (MessageType.ORDER_DONE, "ord-1", "done")]
