"""A worker's key: what the gate lets through, and the authorized_keys line it gets."""

import io
import json
import os

import pytest

from mulebox.common.protocol import encode
from mulebox.coordinator import rpc, worker_keys
from mulebox.coordinator.worker_keys import GateRefused, authorize, gate_command, key_line

from .helpers import request, submit_body

JOB = "job-01JC3X0000000000000000000Z"
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleExampleExampleExampleExample0 mulebox-worker"


@pytest.mark.parametrize("original, expected", [
    (".mulebox/bin/mulebox rpc", ("rpc", None)),
    ("/home/alice/.mulebox/bin/mulebox rpc", ("rpc", None)),
    (f".mulebox/bin/mulebox rpc-download {JOB}", ("rpc-download", JOB)),
])
def test_gate_lets_worker_requests_through(original, expected):
    assert gate_command(original) == expected


@pytest.mark.parametrize("original", [
    None, "", "bash", "sh -c 'mulebox rpc'", ".mulebox/bin/mulebox rpc; id",
    ".mulebox/bin/mulebox rpc-upload job x", ".mulebox/bin/mulebox rpc-download ../etc",
    ".mulebox/bin/mulebox project-home reset x --yes", ".mulebox/bin/mulebox rpc extra",
    "'unclosed",
])
def test_gate_refuses_anything_else(original):
    with pytest.raises(GateRefused):
        gate_command(original)


def test_rpc_with_a_worker_key_refuses_client_requests(store, staging):
    out = io.BytesIO()
    msg = request("submit", **submit_body())
    code = rpc.run_rpc(store, staging, io.BytesIO(encode(msg)), out, io.StringIO(),
                       clock=lambda: 1000.0, allowed=worker_keys.WORKER_MESSAGES)
    reply = json.loads(out.getvalue())
    assert code != 0 and reply["type"] == "error" and "worker key" in reply["body"]["message"]


def test_key_line_has_no_shell_and_no_forwarding():
    line = key_line("build-2", KEY, "/home/alice/.mulebox/bin/mulebox")
    assert line.startswith('command="/home/alice/.mulebox/bin/mulebox ssh-gate",restrict ssh-ed25519 ')
    assert line.endswith(" mulebox-worker:build-2")


@pytest.mark.parametrize("name, key", [
    ("build 2", KEY), ("-x", KEY), ("build-2", "not a key"), ("build-2", 'ssh-ed25519 AA"A'),
    ("build-2", KEY + "\nssh-ed25519 AAAA second"), ("build-2", "ssh-dss AAAA"),
])
def test_key_line_refuses_bad_input(name, key):
    with pytest.raises(GateRefused):
        key_line(name, key, "/home/alice/.mulebox/bin/mulebox")


def test_authorize_replaces_only_its_own_line(tmp_path):
    folder = tmp_path / ".ssh"
    folder.mkdir()
    (folder / "authorized_keys").write_text("ssh-ed25519 AAAAmine alice@laptop\n")
    authorize("build-2", KEY, tmp_path)
    path = authorize("build-2", KEY.replace("Example0", "Example1"), tmp_path)
    lines = path.read_text().splitlines()
    assert lines[0] == "ssh-ed25519 AAAAmine alice@laptop"
    assert len(lines) == 2 and "Example1" in lines[1]
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert [p.name for p in folder.iterdir()] == ["authorized_keys"]


def test_authorize_makes_a_private_ssh_folder(tmp_path):
    authorize("build-2", KEY, tmp_path)
    assert os.stat(tmp_path / ".ssh").st_mode & 0o777 == 0o700


def test_deauthorize_takes_off_only_that_worker(tmp_path):
    folder = tmp_path / ".ssh"
    folder.mkdir()
    (folder / "authorized_keys").write_text("ssh-ed25519 AAAAmine alice@laptop\n")
    authorize("build-2", KEY, tmp_path)
    authorize("build-3", KEY, tmp_path)
    assert worker_keys.deauthorize("build-2", tmp_path) is True
    lines = (folder / "authorized_keys").read_text().splitlines()
    assert lines[0] == "ssh-ed25519 AAAAmine alice@laptop" and lines[1].endswith(":build-3")
    assert len(lines) == 2 and worker_keys.deauthorize("build-2", tmp_path) is False
