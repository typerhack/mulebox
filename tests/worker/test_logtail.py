"""Log tailing: incremental UTF-8, redaction before sending, 64 KiB chunks, byte offsets."""

import pytest

from mulebox.common.protocol import Message, MessageType
from mulebox.worker.link import LinkError, request
from mulebox.worker.logtail import MAX_CHUNK_BYTES, LogTailer, split_utf8

TOKEN = "ghp_" + "A" * 36


class Sink:
    def __init__(self):
        self.chunks = []
        self.fail = False
        self.refuse = False

    def __call__(self, msg):
        if self.fail:
            raise LinkError("down")
        if self.refuse:
            return Message(MessageType.ERROR, msg.request_id, {"code": "conflict", "message": "x"})
        self.chunks.append(msg.body)
        return Message(MessageType.STATUS_OK, msg.request_id, {"job_id": "j", "state": "running"})

    def text(self):
        return "".join(c["data"] for c in self.chunks)


def _tailer(tmp_path):
    return LogTailer(tmp_path / "out.log", "job-1", "att-1", request)


def _append(tmp_path, data: bytes):
    with open(tmp_path / "out.log", "ab") as fh:
        fh.write(data)


def test_split_utf8_respects_limit_and_characters():
    data = ("a" * 5 + "é" * 10).encode()
    pieces = split_utf8(data, limit=6)
    assert all(len(p) <= 6 for p in pieces)
    assert b"".join(pieces) == data
    assert all(p.decode() for p in pieces)


def test_redacts_token_split_across_reads_and_offsets_are_bytes(tmp_path):
    tailer, sink = _tailer(tmp_path), Sink()
    tailer.read_new()  # no file yet
    _append(tmp_path, ("café " + TOKEN[:10]).encode())
    tailer.read_new()
    tailer.send(sink)
    _append(tmp_path, (TOKEN[10:] + " done\n").encode() + "é".encode()[:1])
    tailer.read_new()
    tailer.send(sink)
    _append(tmp_path, "é".encode()[1:] + b"tail")
    tailer.finish()
    tailer.send(sink)
    assert sink.text() == "café [redacted] done\nétail"
    assert TOKEN not in sink.text()
    offset = 0
    for chunk in sink.chunks:
        assert chunk["offset"] == offset and chunk["attempt_id"] == "att-1"
        offset += len(chunk["data"].encode())


def test_invalid_utf8_is_replaced(tmp_path):
    tailer, sink = _tailer(tmp_path), Sink()
    _append(tmp_path, b"bad \xff byte\n")
    tailer.finish()
    tailer.send(sink)
    assert sink.text() == "bad � byte\n"


def test_large_output_is_chunked(tmp_path):
    tailer, sink = _tailer(tmp_path), Sink()
    _append(tmp_path, ("x" * 100 + "\n").encode() * 2000)
    tailer.finish()
    tailer.send(sink)
    assert len(sink.chunks) > 3
    assert all(len(c["data"].encode()) <= MAX_CHUNK_BYTES for c in sink.chunks)
    assert len(sink.text()) == 101 * 2000


def test_transport_failure_keeps_queue_error_reply_drops_it(tmp_path):
    tailer, sink = _tailer(tmp_path), Sink()
    tailer.note("hello\n")
    sink.fail = True
    with pytest.raises(LinkError):
        tailer.send(sink)
    assert not tailer.sent_all
    sink.fail = False
    tailer.send(sink)
    assert sink.text() == "hello\n" and tailer.sent_all
    sink.refuse = True
    tailer.note("more\n")
    tailer.send(sink)
    assert tailer.dropped and tailer.sent_all
