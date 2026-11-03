import io

from mulebox.common.protocol import JobState, Outcome
from mulebox.coordinator import leases, recovery

from .helpers import claimed, queued, snapshot, submit

T0 = 1000.0


def test_recover_interrupts_only_expired_active_jobs(store, staging):
    stale = claimed(store, staging, now=T0)
    fresh = claimed(store, staging, now=T0, worker="wrk-b")
    waiting = queued(store, staging, now=T0)
    now = T0 + leases.WORKER_LEASE_S + 5
    leases.renew_worker(store, fresh["job_id"], fresh["attempt_id"], now - 1)
    assert recovery.recover(store, now, staging) == [stale["job_id"]]
    assert store.get_job(stale["job_id"])["outcome"] == Outcome.INTERRUPTED
    assert store.get_job(fresh["job_id"])["state"] == JobState.STARTING
    assert store.get_job(waiting)["state"] == JobState.QUEUED  # never replayed or dropped


def test_recover_removes_uploads_nobody_needs(store, staging):
    stale = claimed(store, staging, now=T0)
    keep = queued(store, staging, now=T0)
    uploading = submit(store, staging, now=T0)
    unknown = "job-01JC3X0000000000000000000Z"
    data, digest = snapshot()
    staging.write_upload(unknown, io.BytesIO(data), digest)
    (staging.uploads_dir / f".{uploading}.ffff.part").write_bytes(b"in progress")
    (staging.uploads_dir / f".{keep}.eeee.part").write_bytes(b"left over")
    recovery.recover(store, T0 + 1000, staging)
    names = sorted(p.name for p in staging.uploads_dir.iterdir())
    assert names == sorted([f"{keep}.tar.gz", f".{uploading}.ffff.part"])
    assert stale["job_id"] not in " ".join(names)
