"""`mulebox run --take` on the worker: what a passed run brings back, and how it is sent."""

import base64
import os

import pytest

from mulebox.common.protocol import Message, MessageType
from mulebox.common.take_paths import CHUNK_BYTES
from mulebox.worker import take_back
from mulebox.worker.link import LinkError

from .test_agent import agent, clock, executor, result_of, run_until  # noqa: F401
from .fakes import claim_body


def test_read_files_takes_plain_files_and_names_the_rest(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "composer.lock").write_bytes(b"{}")
    (tmp_path / "outside").write_text("secret")
    os.symlink(tmp_path / "outside", tmp_path / "link.lock")
    (tmp_path / "dir.lock").mkdir()
    notes = []
    found = take_back.read_files(tmp_path, ["api/composer.lock", "gone.lock", "link.lock",
                                            "dir.lock", "../x"], notes.append)
    assert found == [(0, b"{}")]
    text = "".join(notes)
    assert "taken back: api/composer.lock (2 B)" in text
    assert "gone.lock is not there" in text and "link.lock goes through a link" in text
    assert "dir.lock is not a plain file" in text and "../x must stay inside" in text


def test_chunks_cover_the_file_and_an_empty_one():
    data = b"a" * (CHUNK_BYTES + 3)
    parts = take_back.chunks([(0, data), (1, b"")])
    assert [(i, off, len(d)) for i, off, d in parts] == [(0, 0, CHUNK_BYTES),
                                                         (0, CHUNK_BYTES, 3), (1, 0, 0)]


def test_send_resumes_where_a_lost_link_stopped():
    pending = take_back.chunks([(0, b"abc"), (1, b"de")])
    sent, down = [], [False, True]  # the second call finds the link down, once

    def call(msg: Message) -> Message:
        if down and down.pop(0):
            raise LinkError("down")
        sent.append((msg.body["index"], base64.b64decode(msg.body["data"])))
        return Message(MessageType.STATUS_OK, msg.request_id, {"job_id": "job-x", "state": "cleaning"})

    with pytest.raises(LinkError):
        take_back.send("job-x", "att-x", pending, call)
    assert len(pending) == 1
    take_back.send("job-x", "att-x", pending, call)
    assert sent == [(0, b"abc"), (1, b"de")] and pending == []


def test_a_passed_job_sends_its_files_before_the_result(agent, fake_link):  # noqa: F811
    body = claim_body(["bash", "-c", "echo new > made.lock"])
    body["take"] = ["made.lock", "missing.lock"]
    fake_link.claims.append(body)
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert result_of(fake_link)["outcome"] == "passed"
    kinds = [m.type for m in fake_link.sent]
    taken = fake_link.of_type(MessageType.TAKEN)
    assert [(m.body["index"], base64.b64decode(m.body["data"])) for m in taken] == [(0, b"new\n")]
    assert kinds.index(MessageType.TAKEN) < kinds.index(MessageType.RESULT)
    assert "not taken back: missing.lock" in fake_link.log_text()


def test_a_failed_job_sends_nothing(agent, fake_link):  # noqa: F811
    body = claim_body(["bash", "-c", "echo new > made.lock; exit 1"])
    body["take"] = ["made.lock"]
    fake_link.claims.append(body)
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert not fake_link.of_type(MessageType.TAKEN)
