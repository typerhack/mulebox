"""A held project starts no job, and a hold cannot outlive its use."""

import pytest

from mulebox.coordinator import holds, queue
from mulebox.coordinator.errors import Conflict

from .helpers import claimed, queued


def claim(store, now):
    return queue.claim(store, "wrk-a", [], 2, cluster_slots=5, now=now)


def test_a_held_project_waits_and_others_pass(store, staging):
    queued(store, staging, now=10.0)
    other = queued(store, staging, now=11.0, project="other-app")
    holds.take(store, "example-app", 20.0)
    assert claim(store, 21.0)["job_id"] == other


def test_a_released_project_goes_on(store, staging):
    job = queued(store, staging, now=10.0)
    holds.take(store, "example-app", 20.0)
    holds.release(store, "example-app")
    assert claim(store, 21.0)["job_id"] == job


def test_a_hold_ends_by_itself(store, staging):
    job = queued(store, staging, now=10.0)
    holds.take(store, "example-app", 20.0)
    assert claim(store, 20.0 + holds.HOLD_S + 1)["job_id"] == job


def test_a_running_job_refuses_the_hold(store, staging):
    claimed(store, staging, now=10.0)
    with pytest.raises(Conflict, match="running"):
        holds.take(store, "example-app", 20.0)
