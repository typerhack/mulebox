import io
import json

from mulebox.common.protocol import encode
from mulebox.coordinator import api, leases
from mulebox.coordinator.watch import HeartbeatReader, watch

from .helpers import queued, request

T0 = 1000.0


class FakeClock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now


def lines(out: io.BytesIO) -> list[dict]:
    return [json.loads(line) for line in out.getvalue().splitlines()]


def test_watch_streams_until_result(store, staging):
    job_id = queued(store, staging)
    clock = FakeClock()
    state = {}

    def worker_step(index):
        if index == 0:
            reply = api.handle(store, staging, request(
                "claim", worker="wrk-a", capabilities=[], free_slots=1), clock())
            state.update(job_id=job_id, attempt_id=reply.body["attempt_id"])
        elif index == 1:
            api.handle(store, staging, request("job_update", state="running", **state), clock())
            api.handle(store, staging, request("log_chunk", offset=0, data="one\n", **state),
                       clock())
        elif index == 2:
            api.handle(store, staging, request("log_chunk", offset=4, data="two\n", **state),
                       clock())
            api.handle(store, staging, request(
                "result", outcome="failed", exit_code=1, duration_s=3.0, **state), clock())

    calls = []

    def sleep(seconds):
        assert seconds == 0.5
        worker_step(len(calls))
        calls.append(seconds)
        clock.now += seconds

    out = io.BytesIO()
    msg = request("watch", job_id=job_id, offset=0)
    assert watch(store, staging, msg, io.BytesIO(), out, clock=clock, sleep=sleep) == 0
    stream = lines(out)
    assert {line["request_id"] for line in stream} == {msg.request_id}
    summary = [(line["type"], line["body"].get("state"), line["body"].get("data"))
               for line in stream]
    assert summary == [
        ("status_ok", "queued", None),
        ("status_ok", "starting", None),
        ("log_chunk", "running", "one\n"),
        ("status_ok", "running", None),
        ("log_chunk", "finished", "two\n"),
        ("status_ok", "finished", None),
        ("result", "finished", None),
    ]
    assert stream[1]["body"].get("position") is None
    assert stream[0]["body"]["position"] == 1
    result = stream[-1]["body"]
    assert result["outcome"] == "failed" and result["exit_code"] == 1
    assert result["duration_s"] == 3.0
    assert stream[4]["body"]["eof"] is True


def test_watch_resumes_from_offset(store, staging):
    job_id = queued(store, staging)
    staging.append_log(job_id, 0, b"old new")
    api.handle(store, staging, request("cancel", job_id=job_id), T0)
    out = io.BytesIO()
    watch(store, staging, request("watch", job_id=job_id, offset=4), io.BytesIO(), out,
          clock=FakeClock(), sleep=lambda s: None)
    assert [line["body"].get("data") for line in lines(out)][0] == "new"


def test_watch_with_lease_renews_at_start(store, staging):
    job_id = queued(store, staging)
    clock = FakeClock(T0 + 30)
    seen = []

    def sleep(_):
        seen.append(store.get_job(job_id)["client_lease_until"])
        api.handle(store, staging, request("cancel", job_id=job_id), clock())

    out = io.BytesIO()
    watch(store, staging, request("watch", job_id=job_id, offset=0, lease=True),
          io.BytesIO(), out, clock=clock, sleep=sleep)
    assert seen == [T0 + 30 + leases.CLIENT_LEASE_S]
    assert lines(out)[-1]["type"] == "result"


def test_heartbeat_reader_renews_client_lease(store, staging):
    job_id = queued(store, staging)
    beat = encode(request("heartbeat", job_id=job_id, lease="client"))
    stdin = io.BytesIO(beat + b"not json\n" + beat)
    reader = HeartbeatReader(stdin, store, job_id, True, FakeClock(T0 + 500))
    reader.run()
    assert reader.renewals == 2
    assert store.get_job(job_id)["client_lease_until"] == T0 + 500 + leases.CLIENT_LEASE_S


def test_heartbeat_reader_without_lease_only_reads(store, staging):
    job_id = queued(store, staging)
    beat = encode(request("heartbeat", job_id=job_id, lease="client"))
    reader = HeartbeatReader(io.BytesIO(beat), store, job_id, False, FakeClock(T0 + 500))
    reader.run()
    assert reader.renewals == 0
    assert store.get_job(job_id)["client_lease_until"] == T0 + leases.CLIENT_LEASE_S


def test_heartbeat_reader_stops_on_oversized_line(store, staging):
    job_id = queued(store, staging)
    reader = HeartbeatReader(io.BytesIO(b"x" * (2 << 20)), store, job_id, True, FakeClock())
    reader.run()
    assert reader.renewals == 0
