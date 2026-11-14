"""Branches no dev machine has any more, from the lists jobs carry (coordinator/branch_lists.py)."""

import pytest

from mulebox.common.protocol import MessageType
from mulebox.coordinator import api, branch_lists

from .helpers import request, submit, submit_body

DAY = 86400.0


def gone(store, now):
    with store.read() as conn:
        return branch_lists.gone(conn, now)


def test_a_branch_the_dev_machine_no_longer_has_is_gone(store, staging):
    submit(store, staging, now=10.0, branch="feature/a", branches=["main", "feature/a"])
    submit(store, staging, now=20.0, branch="main", branches=["main", "feature/a"])
    assert gone(store, 30.0) == {}
    submit(store, staging, now=40.0, branch="main", branches=["main"])  # feature/a deleted
    assert gone(store, 50.0) == {"example-app": ["feature/a"]}


def test_another_dev_machine_still_having_it_keeps_it(store, staging):
    submit(store, staging, now=10.0, branch="feature/a", branches=["feature/a"])
    submit(store, staging, now=11.0, branch="x", client="bob@laptop", branches=["x", "feature/a"])
    submit(store, staging, now=20.0, branch="main", branches=["main"])
    assert gone(store, 30.0) == {}


def test_a_dev_machine_that_sends_no_list_is_never_judged(store, staging):
    submit(store, staging, now=10.0, branch="old", client="carol@old")  # an older mulebox
    submit(store, staging, now=20.0, branch="main", branches=["main"])
    assert gone(store, 30.0) == {}


def test_a_list_older_than_the_branchs_last_job_says_nothing(store, staging):
    submit(store, staging, now=10.0, branch="main", branches=["main"])
    submit(store, staging, now=20.0, branch="new", client="bob@laptop")  # no list from bob
    submit(store, staging, now=30.0, branch="main", client="bob@laptop", branches=["main"])
    assert gone(store, 40.0) == {"example-app": ["new"]}
    submit(store, staging, now=50.0, branch="new", client="bob@laptop")  # a job after the list
    assert gone(store, 60.0) == {}


def test_lists_older_than_two_weeks_count_no_more(store, staging):
    submit(store, staging, now=10.0, branch="feature/a", branches=["feature/a"])
    submit(store, staging, now=20.0, branch="main", branches=["main"])
    assert gone(store, 20.0 + 15 * DAY) == {}


@pytest.mark.parametrize("value", ["main", [3], ["x" * 300], [""]])
def test_a_bad_list_is_refused(store, staging, value):
    reply = api.handle(store, staging, request("submit", **submit_body(branches=value)), 1.0)
    assert reply.type is MessageType.ERROR
