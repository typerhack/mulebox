import hashlib
import shlex

import pytest

from mulebox.client.remote import CoordinatorError, Remote, remote_program, request
from mulebox.common.config import ClientConfig
from mulebox.common.protocol import MessageType
from mulebox.common.ssh import SSHUnavailable

JOB = "job-01JC3X0000000000000000ABCD"


def test_remote_program_drops_home_prefix():
    assert remote_program("~/.mulebox/bin/mulebox") == ".mulebox/bin/mulebox"
    assert remote_program("/opt/mulebox/bin/mulebox") == "/opt/mulebox/bin/mulebox"


def test_call_sends_one_line_and_checks_the_reply(fake, client_config):
    fake.scenario()
    msg = request(MessageType.STATUS, job_id=JOB)
    reply = Remote(client_config).call(msg)
    assert reply.type is MessageType.STATUS_OK and reply.request_id == msg.request_id
    assert fake.requests()[0]["body"] == {"job_id": JOB}
    argv = fake.argv()
    assert argv[:2] == ["-T", "-o"] and "build-1" in argv
    assert shlex.split(argv[argv.index("--") + 1]) == [".mulebox/bin/mulebox", "rpc"]


def test_error_reply_raises_with_code(fake, client_config):
    fake.scenario(error="not_found")
    with pytest.raises(CoordinatorError) as info:
        Remote(client_config).call(request(MessageType.STATUS, job_id=JOB))
    assert info.value.code == "not_found"


def test_unreachable_raises_ssh_unavailable(fake, client_config):
    fake.scenario(down=True)
    with pytest.raises(SSHUnavailable):
        Remote(client_config).call(request(MessageType.STATUS, job_id=JOB))
    with pytest.raises(SSHUnavailable):
        list(Remote(client_config).watch(JOB))


def test_upload_streams_the_file(fake, client_config, tmp_path):
    fake.scenario()
    path = tmp_path / "snap.tar.gz"
    data = b"\x1f\x8b" + bytes(range(256)) * 4096
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    reply = Remote(client_config).upload(JOB, path, digest)
    assert reply.body["state"] == "queued"
    assert fake.upload() == data
    command = shlex.split(fake.argv()[-1])
    assert command[1:] == ["rpc-upload", JOB, digest]


def test_upload_rejected(fake, client_config, tmp_path):
    fake.scenario()
    path = tmp_path / "snap.tar.gz"
    path.write_bytes(b"data")
    with pytest.raises(CoordinatorError, match="sha256 mismatch"):
        Remote(client_config).upload(JOB, path, "0" * 64)


def test_watch_yields_messages_and_sends_heartbeats(fake, client_config):
    fake.scenario(log=["a\n", "b\n"], delay_s=0.3)
    messages = list(Remote(client_config, heartbeat_s=0.1).watch(JOB, 0, lease=True))
    kinds = [m.type for m in messages]
    assert kinds[-1] is MessageType.RESULT
    assert kinds.count(MessageType.LOG_CHUNK) == 2
    sent = fake.requests()
    assert sent[0]["type"] == "watch"
    assert sent[0]["body"] == {"job_id": JOB, "offset": 0, "lease": True}
    beats = [r for r in sent[1:] if r["type"] == "heartbeat"]
    assert beats and beats[0]["body"] == {"job_id": JOB, "lease": "client"}


def test_watch_without_result_is_a_protocol_error(fake, client_config, monkeypatch):
    import mulebox.client.remote as module

    fake.scenario(log=[])
    real = module._decode_line

    def drop_result(line):
        msg = real(line)
        if msg.type is MessageType.RESULT:
            return real(b'{"body":{"job_id":"x","state":"queued"},"request_id":"r",'
                        b'"type":"status_ok","v":1}\n')
        return msg

    monkeypatch.setattr(module, "_decode_line", drop_result)
    with pytest.raises(CoordinatorError, match="without a result"):
        list(Remote(client_config).watch(JOB))


def test_garbage_reply_is_a_protocol_error(fake, client_config, monkeypatch, tmp_path):
    from mulebox.common import ssh

    script = tmp_path / "garbage-ssh"
    script.write_text("#!/bin/sh\ncat >/dev/null\necho not-json\n")
    script.chmod(0o755)
    monkeypatch.setattr(ssh, "SSH_BINARY", str(script))
    with pytest.raises(CoordinatorError, match="bad reply"):
        Remote(ClientConfig(coordinator="build-1")).call(request(MessageType.QUEUE))
