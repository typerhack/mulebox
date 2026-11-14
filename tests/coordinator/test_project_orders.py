"""`project reset` and `clean` on every node through orders (coordinator/project_orders.py)."""

from mulebox.common.protocol import MessageType
from mulebox.coordinator import api, project_orders

from .helpers import claimed, queued, request
from .test_node_choice import claim, ran_on, seen


def order(store, staging, now, **body):
    return api.handle(store, staging, request("project_order", **body), now)


def answer(store, staging, order_id, now, code=0, output="done"):
    reply = api.handle(store, staging, request(
        "order_done", order_id=order_id, exit_code=code, output=output), now)
    assert reply.type is MessageType.ORDER_DONE_OK, reply.body


def orders_of(store, staging, worker, now):
    return claim(store, staging, worker, now, free=0).body.get("orders", [])


def test_one_order_per_online_node_and_each_answer(store, staging):
    seen(store, staging, now=1.0, **{"build-1": 1, "build-2": 1})
    seen(store, staging, now=1000.0, **{"build-1": 1})  # build-2 is offline by now
    reply = order(store, staging, 1001.0, action="reset", project="example-app")
    assert reply.type is MessageType.PROJECT_ORDER_OK, reply.body
    assert reply.body["nodes"] == ["build-1"] and reply.body["offline"] == ["build-2"]
    taken = orders_of(store, staging, "build-1", 1002.0)
    assert [o["action"] for o in taken] == ["reset"] and taken[0]["project"] == "example-app"
    assert orders_of(store, staging, "build-1", 1003.0) == []  # handed out once
    group = reply.body["group"]
    assert order(store, staging, 1004.0, group=group).body["done"] is False
    answer(store, staging, taken[0]["order_id"], 1005.0, output="no folder at /x")
    body = order(store, staging, 1006.0, group=group).body
    assert body["done"] and body["answers"][0]["output"] == "no folder at /x"


def test_a_clean_carries_the_branch_history(store, staging):
    seen(store, staging, now=1.0, **{"build-1": 1})
    ran_on(store, "build-1", "main", now=5.0)
    order(store, staging, 10.0, action="clean", days=7)
    taken = orders_of(store, staging, "build-1", 11.0)
    assert taken[0]["days"] == 7 and taken[0]["used"]["example-app"]["main"] == 5.0


def test_reset_yes_holds_the_project_until_every_node_answered(store, staging):
    seen(store, staging, now=1.0, **{"build-1": 2})
    reply = order(store, staging, 10.0, action="reset", project="example-app", yes=True)
    queued(store, staging, now=11.0)
    first = claim(store, staging, "build-1", 12.0)
    assert first.type is MessageType.CLAIM_NONE  # held; the order comes with the answer
    taken = first.body["orders"]
    base = staging.bases_dir / staging._base_name("example-app")
    base.write_bytes(b"base")
    answer(store, staging, taken[0]["order_id"], 14.0)
    assert not base.exists()
    assert order(store, staging, 15.0, group=reply.body["group"]).body["done"]
    assert claim(store, staging, "build-1", 16.0).type is MessageType.CLAIM_OK


def test_reset_yes_is_refused_while_a_job_of_it_runs(store, staging):
    claimed(store, staging, now=10.0, worker="build-1")
    reply = order(store, staging, 11.0, action="reset", project="example-app", yes=True)
    assert reply.type is MessageType.ERROR and "has a job running" in reply.body["message"]


def test_a_node_that_never_answers_counts_as_lost(store, staging):
    seen(store, staging, now=1.0, **{"build-1": 1})
    reply = order(store, staging, 2.0, action="clean")
    body = order(store, staging, 3.0 + project_orders.ANSWER_S, group=reply.body["group"]).body
    assert body["done"] and body["answers"][0]["lost"]


def test_a_bad_order_says_why(store, staging):
    reply = order(store, staging, 1.0, action="format")
    assert reply.type is MessageType.ERROR and "reset, clean" in reply.body["message"]
    assert order(store, staging, 1.0, group="grp-none").type is MessageType.ERROR
