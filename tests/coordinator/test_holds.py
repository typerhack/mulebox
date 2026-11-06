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


def test_a_draining_machine_starts_nothing_and_lists_what_runs(store, staging):
    running = claimed(store, staging, now=10.0)
    queued(store, staging, now=11.0, project="other-app")
    assert holds.drain(store, 100.0) == [running["job_id"]]
    assert claim(store, 20.0) is None


def test_a_drain_ends_by_itself_and_on_request(store, staging):
    job = queued(store, staging, now=10.0)
    holds.drain(store, 30.0)
    assert claim(store, 40.0)["job_id"] == job
    other = queued(store, staging, now=41.0, project="other-app")
    holds.drain(store, 100.0)
    holds.undrain(store)
    assert claim(store, 50.0)["job_id"] == other
