import os

import pytest

from mulebox.common.protocol import JobState, Outcome
from mulebox.coordinator import leases, queue
from mulebox.coordinator.errors import BadRequest, Conflict

from .helpers import claimed, queued, submit

T0 = 1000.0


def test_renew_client_extends_lease(store, staging):
    job_id = submit(store, staging, now=T0)
    job = leases.renew_client(store, job_id, T0 + 50)
    assert job["client_lease_until"] == T0 + 50 + leases.CLIENT_LEASE_S


def test_renew_worker_checks_attempt(store, staging):
    claim = claimed(store, staging, now=T0)
    job = leases.renew_worker(store, claim["job_id"], claim["attempt_id"], T0 + 60)
    assert job["worker_lease_until"] == T0 + 60 + leases.WORKER_LEASE_S
    with pytest.raises(Conflict):
        leases.renew_worker(store, claim["job_id"], "att-old", T0 + 60)
    with pytest.raises(BadRequest):
        leases.renew_worker(store, claim["job_id"], None, T0 + 60)


def test_nothing_expires_early(store, staging):
    submit(store, staging, now=T0)
    queued(store, staging, now=T0)
    claimed(store, staging, now=T0)
    assert leases.expire(store, T0 + 100, staging) == []


def test_an_expired_client_lease_stops_nothing(store, staging):
    job_id = queued(store, staging, now=T0)
    claim = claimed(store, staging, now=T0)
    later = T0 + leases.CLIENT_LEASE_S + 1
    leases.renew_worker(store, claim["job_id"], claim["attempt_id"], later - 10)
    assert leases.expire(store, later, staging) == []
    assert store.get_job(job_id)["cancel_requested"] is False
    assert store.get_job(claim["job_id"])["cancel_requested"] is False


def test_expired_worker_lease_interrupts(store, staging):
    claim = claimed(store, staging, now=T0)
    leases.renew_client(store, claim["job_id"], T0 + 100)
    finished = leases.expire(store, T0 + queue.WORKER_LEASE_S + 1, staging)
    assert finished == [claim["job_id"]]
    job = store.get_job(claim["job_id"])
    assert job["outcome"] == Outcome.INTERRUPTED and job["worker_lease_until"] is None


def test_uploading_job_times_out_but_ignores_client_lease(store, staging):
    job_id = submit(store, staging, now=T0)
    assert leases.expire(store, T0 + leases.CLIENT_LEASE_S + 1, staging) == []
    assert store.get_job(job_id)["state"] == JobState.UPLOADING
    assert leases.expire(store, T0 + leases.UPLOAD_TIMEOUT_S + 1, staging) == [job_id]
    assert store.get_job(job_id)["outcome"] == Outcome.INTERRUPTED


def test_expire_is_repeatable(store, staging):
    claimed(store, staging, now=T0)
    now = T0 + 10_000
    assert len(leases.expire(store, now, staging)) == 1
    assert leases.expire(store, now, staging) == []
