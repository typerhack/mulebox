import io
import json
import os

from mulebox.common.protocol import encode
from mulebox.coordinator import rpc
from mulebox.coordinator.lineio import MAX_LINE_BYTES

from .helpers import claimed, queued, request, snapshot, submit, submit_body

MISSING = "job-01JC3X0000000000000000000Z"


def run(store, staging, data: bytes):
    out, err = io.BytesIO(), io.StringIO()
    code = rpc.run_rpc(store, staging, io.BytesIO(data), out, err, clock=lambda: 1000.0,
                       sleep=lambda s: None)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    return code, replies, err.getvalue()


def test_rpc_submit_one_line(store, staging):
    msg = request("submit", **submit_body())
    code, replies, err = run(store, staging, encode(msg))
    assert code == 0 and err == ""
    assert len(replies) == 1 and replies[0]["type"] == "submit_ok"
    assert replies[0]["request_id"] == msg.request_id


def test_rpc_reads_only_one_line(store, staging):
    first = encode(request("submit", **submit_body()))
    code, replies, _ = run(store, staging, first + first)
    assert code == 0 and len(replies) == 1


def test_rpc_error_reply_exits_4_and_notes_stderr(store, staging):
    code, replies, err = run(store, staging, encode(request("status", job_id=MISSING)))
    assert code == 4
    assert replies[0]["type"] == "error" and replies[0]["body"]["code"] == "not_found"
    assert "not_found" in err


def test_rpc_bad_input(store, staging):
    for data, expected in [
        (b"", "bad_request"),
        (b"{not json}\n", "bad_request"),
        (b'{"v": 9, "type": "status", "request_id": "r", "body": {}}\n', "bad_request"),
        (b"x" * (MAX_LINE_BYTES + 10), "too_large"),
    ]:
        code, replies, _ = run(store, staging, data)
        assert code == 4
        assert replies[0]["body"]["code"] == expected
        assert "Traceback" not in json.dumps(replies)


def test_rpc_line_at_cap_is_accepted(store, staging):
    msg = encode(request("status", job_id=MISSING))
    padded = msg[:-1] + b" " * (MAX_LINE_BYTES - len(msg)) + b"\n"
    assert len(padded) == MAX_LINE_BYTES
    _, replies, _ = run(store, staging, padded)
    assert replies[0]["body"]["code"] == "not_found"


def test_rpc_internal_error_never_traceback(store, staging, monkeypatch):
    monkeypatch.setattr(rpc.api, "handle", lambda *a, **k: 1 / 0)
    code, replies, _ = run(store, staging, encode(request("status", job_id=MISSING)))
    assert code == 4 and replies[0]["body"]["code"] == "internal"


def test_rpc_watch_streams(store, staging):
    job_id = queued(store, staging)
    staging.append_log(job_id, 0, b"log\n")
    store_cancel = encode(request("cancel", job_id=job_id))
    run(store, staging, store_cancel)
    code, replies, _ = run(store, staging, encode(request("watch", job_id=job_id, offset=0)))
    assert code == 0
    assert [r["type"] for r in replies] == ["log_chunk", "status_ok", "result"]


def test_rpc_watch_unknown_job(store, staging):
    code, replies, _ = run(store, staging, encode(request("watch", job_id=MISSING, offset=0)))
    assert code == 4 and replies == [replies[0]] and replies[0]["body"]["code"] == "not_found"


def upload(store, staging, job_id, data, digest):
    out, err = io.BytesIO(), io.StringIO()
    code = rpc.run_upload(store, staging, job_id, digest, io.BytesIO(data), out, err,
                          clock=lambda: 1000.0)
    return code, json.loads(out.getvalue())


def test_upload_queues_job(store, staging):
    job_id = submit(store, staging)
    data, digest = snapshot()
    code, reply = upload(store, staging, job_id, data, digest)
    assert code == 0
    assert reply["type"] == "status_ok" and reply["body"]["state"] == "queued"
    assert reply["body"]["position"] == 1
    assert store.get_job(job_id)["upload_sha256"] == digest


def test_upload_refused_unless_uploading(store, staging):
    job_id = queued(store, staging)
    data, digest = snapshot()
    code, reply = upload(store, staging, job_id, data, digest)
    assert code == 4 and reply["body"]["code"] == "conflict"
    code, reply = upload(store, staging, MISSING, data, digest)
    assert reply["body"]["code"] == "not_found"
    code, reply = upload(store, staging, "../../x", data, digest)
    assert reply["body"]["code"] == "bad_request"


def test_upload_bad_hash_keeps_job_uploading(store, staging):
    job_id = submit(store, staging)
    code, reply = upload(store, staging, job_id, b"data", "0" * 64)
    assert code == 4 and reply["body"]["code"] == "bad_request"
    assert store.get_job(job_id)["state"] == "uploading"
    assert os.listdir(staging.uploads_dir) == []


def test_upload_cancelled_meanwhile_removes_file(store, staging, monkeypatch):
    job_id = submit(store, staging)
    data, digest = snapshot()
    original = staging.write_upload

    def write_then_cancel(*args, **kwargs):
        size = original(*args, **kwargs)
        run(store, staging, encode(request("cancel", job_id=job_id)))
        return size

    monkeypatch.setattr(staging, "write_upload", write_then_cancel)
    code, reply = upload(store, staging, job_id, data, digest)
    assert reply["body"]["code"] == "conflict"
    assert os.listdir(staging.uploads_dir) == []


def test_download(store, staging):
    claim = claimed(store, staging)
    out, err = io.BytesIO(), io.StringIO()
    assert rpc.run_download(store, staging, claim["job_id"], out, err) == 0
    assert out.getvalue() == snapshot()[0]
    out = io.BytesIO()
    assert rpc.run_download(store, staging, MISSING, out, err) == 4
    assert out.getvalue() == b"" and "not_found" in err.getvalue()
