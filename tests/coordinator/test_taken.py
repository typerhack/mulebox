"""Files a run brings back (`mulebox run --take`): stored from the worker, read by the client."""

import base64

from mulebox.common.take_paths import CHUNK_BYTES
from mulebox.coordinator import retention, taken

from .helpers import claimed
from .test_api import T0, call

DAY = 86400.0


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def ids(claim):
    return {"job_id": claim["job_id"], "attempt_id": claim["attempt_id"]}


def test_claim_carries_the_paths(store, staging):
    claim = claimed(store, staging, take=["api/composer.lock"])
    assert claim["take"] == ["api/composer.lock"]


def test_submit_refuses_a_path_outside_the_project(store, staging):
    from .helpers import submit_body
    for bad in (["../x"], ["/etc/passwd"], ["a/../../b"], [""]):
        reply = call(store, staging, "submit", **submit_body(take=bad))
        assert reply.body["code"] == "bad_request", bad


def test_chunks_resends_and_the_client_read(store, staging):
    claim = claimed(store, staging, take=["a.lock", "b.lock"])
    data = b"x" * (CHUNK_BYTES + 10)
    first, rest = data[:CHUNK_BYTES], data[CHUNK_BYTES:]
    assert call(store, staging, "taken", index=0, offset=0, data=b64(first), **ids(claim)
                ).body["size"] == CHUNK_BYTES
    call(store, staging, "taken", index=0, offset=0, data=b64(first), **ids(claim))  # resent
    assert call(store, staging, "taken", index=0, offset=CHUNK_BYTES, data=b64(rest),
                **ids(claim)).body["size"] == len(data)
    gap = call(store, staging, "taken", index=0, offset=len(data) + 5, data=b64(b"z"), **ids(claim))
    assert gap.body["code"] == "conflict"
    beyond = call(store, staging, "taken", index=2, offset=0, data=b64(b"z"), **ids(claim))
    assert beyond.body["code"] == "bad_request"

    got, offset = b"", 0
    while True:
        body = call(store, staging, "take", job_id=claim["job_id"], index=0, offset=offset).body
        got += base64.b64decode(body["data"])
        offset = len(got)
        if body["eof"]:
            break
    assert got == data
    missing = call(store, staging, "take", job_id=claim["job_id"], index=1, offset=0).body
    assert missing["missing"] is True and missing["eof"] is True


def test_worker_may_not_add_files_after_the_result_or_from_another_attempt(store, staging):
    claim = claimed(store, staging, take=["a.lock"])
    stale = call(store, staging, "taken", index=0, offset=0, data=b64(b"x"),
                 job_id=claim["job_id"], attempt_id="att-01JC3X0000000000000000000Z")
    assert stale.body["code"] == "conflict"
    call(store, staging, "result", outcome="passed", exit_code=0, duration_s=1, **ids(claim))
    late = call(store, staging, "taken", index=0, offset=0, data=b64(b"x"), **ids(claim))
    assert late.body["code"] == "conflict"
    bad = claimed(store, staging, take=["a.lock"])
    reply = call(store, staging, "taken", index=0, offset=0, data="not base64!", **ids(bad))
    assert reply.body["code"] == "bad_request"


def test_files_go_a_day_after_the_job(store, staging):
    claim = claimed(store, staging, now=T0, take=["a.lock"])
    call(store, staging, "taken", index=0, offset=0, data=b64(b"x"), **ids(claim))
    call(store, staging, "result", now=T0, outcome="passed", exit_code=0, duration_s=1,
         **ids(claim))
    retention.sweep(store, staging, T0 + 0.5 * DAY, 30, 365)
    assert taken.job_ids(staging) == {claim["job_id"]}
    retention.sweep(store, staging, T0 + 1.5 * DAY, 30, 365)
    assert taken.job_ids(staging) == set()
