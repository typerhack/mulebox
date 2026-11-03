"""Links: LocalLink calls coordinator.api.handle; SSHLink runs `mulebox rpc` over ssh."""

import sys
import types

import pytest

from mulebox.common import protocol
from mulebox.common.protocol import Message, MessageType
from mulebox.common.ssh import RemoteError, RemoteResult, SSHUnavailable
from mulebox.worker import link as link_mod
from mulebox.worker.link import LinkError, LocalLink, SSHLink, remote_command, request


@pytest.fixture
def fake_api(monkeypatch):
    calls = []
    api = types.ModuleType("mulebox.coordinator.api")

    def handle(store, staging, msg, now):
        calls.append((store, staging, msg, now))
        if msg.body.get("boom"):
            raise RuntimeError("database is locked")
        return Message(MessageType.CLAIM_NONE, msg.request_id, {})

    api.handle = handle
    monkeypatch.setitem(sys.modules, "mulebox.coordinator.api", api)
    import mulebox.coordinator as pkg
    monkeypatch.setattr(pkg, "api", api, raising=False)
    return calls


def test_local_link_calls_handle(fake_api):
    link = LocalLink("STORE", "STAGING")
    msg = request(MessageType.CLAIM, worker="build-1", capabilities=[], free_slots=1)
    reply = link.call(msg)
    assert reply.type is MessageType.CLAIM_NONE and reply.request_id == msg.request_id
    store, staging, sent, now = fake_api[0]
    assert (store, staging, sent) == ("STORE", "STAGING", msg) and now > 1e9


def test_local_link_wraps_failures(fake_api):
    msg = request(MessageType.CLAIM, worker="w", capabilities=[], free_slots=1, boom=True)
    with pytest.raises(LinkError, match="locked"):
        LocalLink(None, None).call(msg)


def test_local_link_fetch_snapshot(tmp_path):
    class Staging:
        def download(self, job_id, dest):
            dest.write_bytes(job_id.encode())

    LocalLink(None, Staging()).fetch_snapshot("job-1", tmp_path / "s.tar.gz")
    assert (tmp_path / "s.tar.gz").read_bytes() == b"job-1"
    with pytest.raises(LinkError):
        LocalLink(None, object()).fetch_snapshot("job-1", tmp_path / "t.tar.gz")


def test_remote_command():
    assert remote_command("~/.mulebox/bin/mulebox") == ".mulebox/bin/mulebox"
    assert remote_command("/opt/mulebox/bin/mulebox") == "/opt/mulebox/bin/mulebox"


def _patch_run(monkeypatch, result=None, exc=None):
    calls = []

    def run_remote(target, argv, **kwargs):
        calls.append((target, list(argv), kwargs))
        if exc:
            raise exc
        return result

    monkeypatch.setattr(link_mod, "run_remote", run_remote)
    return calls


def test_ssh_link_call(monkeypatch):
    msg = request(MessageType.STATUS, job_id="job-1")
    reply = Message(MessageType.STATUS_OK, msg.request_id, {"job_id": "job-1", "state": "queued"})
    calls = _patch_run(monkeypatch, RemoteResult(0, protocol.encode(reply), b""))
    assert SSHLink("build-1", "~/.mulebox/bin/mulebox").call(msg) == reply
    target, argv, kwargs = calls[0]
    assert (target, argv) == ("build-1", [".mulebox/bin/mulebox", "rpc"])
    assert kwargs["stdin"] == protocol.encode(msg)


@pytest.mark.parametrize("exc", [SSHUnavailable("no route"),
                                 RemoteError("x", exit_code=4, stderr=b"")])
def test_ssh_link_failures(monkeypatch, exc):
    _patch_run(monkeypatch, exc=exc)
    with pytest.raises(LinkError):
        SSHLink("build-1", "mulebox").call(request(MessageType.STATUS, job_id="j"))


def test_ssh_link_bad_reply(monkeypatch):
    _patch_run(monkeypatch, RemoteResult(0, b"not json\n", b""))
    with pytest.raises(LinkError, match="bad reply"):
        SSHLink("build-1", "mulebox").call(request(MessageType.STATUS, job_id="j"))


def test_ssh_link_download(monkeypatch, tmp_path):
    calls = _patch_run(monkeypatch, RemoteResult(0, b"TARBYTES", b""))
    SSHLink("build-1", "~/.mulebox/bin/mulebox").fetch_snapshot("job-1", tmp_path / "s")
    assert calls[0][1] == [".mulebox/bin/mulebox", "rpc-download", "job-1"]
    assert (tmp_path / "s").read_bytes() == b"TARBYTES"
