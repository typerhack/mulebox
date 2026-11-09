"""`mulebox run --take` on the client: which paths it accepts, and writing what came back."""

import base64
import io
import os

import pytest

from mulebox.client import take_back
from mulebox.client.remote import request
from mulebox.common.protocol import Message, MessageType


def test_check_refuses_secrets_excludes_and_escapes():
    assert take_back.check(["api/composer.lock", "api/composer.lock"]) == ("api/composer.lock",)
    for bad in (".env", "api/.env.local", "../x", "/etc/hosts", "deploy/id_ed25519"):
        with pytest.raises(ValueError):
            take_back.check([bad])
    with pytest.raises(ValueError, match="exclude"):
        take_back.check(["dist/out.txt"], exclude=["dist/"])


class Coordinator:
    """Plays `take` replies from {index: bytes}, in small chunks."""

    def __init__(self, files, chunk=3):
        self.files, self.chunk = files, chunk

    def call(self, msg: Message) -> Message:
        assert msg.type is MessageType.TAKE
        data = self.files.get(msg.body["index"])
        if data is None:
            body = {"data": "", "size": 0, "eof": True, "missing": True}
        else:
            part = data[msg.body["offset"]:msg.body["offset"] + self.chunk]
            body = {"data": base64.b64encode(part).decode(), "size": len(data),
                    "eof": msg.body["offset"] + len(part) >= len(data)}
        return Message(MessageType.TAKE_OK, msg.request_id, body)


def test_files_are_written_in_place_and_the_missing_one_named(tmp_path):
    (tmp_path / "composer.lock").write_text("old")
    os.chmod(tmp_path / "composer.lock", 0o600)
    err = io.StringIO()
    code = take_back.bring_back(Coordinator({0: b"new lock", 1: b"x"}).call, request, "job-1",
                                ["composer.lock", "web/package-lock.json", "gone.lock"],
                                tmp_path, err)
    assert code == 1
    assert (tmp_path / "composer.lock").read_bytes() == b"new lock"
    assert (tmp_path / "composer.lock").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "web" / "package-lock.json").read_bytes() == b"x"
    text = err.getvalue()
    assert "taken back: composer.lock (8 bytes)" in text and "not taken back: gone.lock" in text
    assert not [p for p in tmp_path.rglob(".*mulebox-*")]


def test_a_symlink_on_the_way_is_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    os.symlink(outside, project / "web")
    err = io.StringIO()
    code = take_back.bring_back(Coordinator({0: b"x"}).call, request, "job-1",
                                ["web/package-lock.json"], project, err)
    assert code == 1 and not (outside / "package-lock.json").exists()
    assert "symlink" in err.getvalue()
