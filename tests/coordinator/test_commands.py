"""The CLI entry points end to end, in a subprocess, against a node config in tmp_path."""

import hashlib
import json
import subprocess
import sys

import pytest

from mulebox import cli
from mulebox.common.protocol import encode

from .helpers import request, submit_body


@pytest.fixture
def node_toml(tmp_path, root_map):
    path = tmp_path / "node.toml"
    roots = "\n".join(f'{key} = "{value}"' for key, value in root_map.items())
    path.write_text(f'name = "build-1"\nroles = ["coordinator", "worker"]\n\n[roots]\n{roots}\n')
    return path


def mulebox(args, node_toml, stdin=b""):
    return subprocess.run(
        [sys.executable, "-m", "mulebox.cli", *args, "--node-config", str(node_toml)],
        input=stdin, capture_output=True, timeout=60,
    )


def test_registered_commands():
    parser = cli.build_parser()
    for argv in (["rpc"], ["rpc-upload", "job-x", "abc"], ["rpc-download", "job-x"],
                 ["coordinator", "serve"]):
        assert callable(parser.parse_args(argv).func)


def test_submit_upload_status_download(node_toml):
    done = mulebox(["rpc"], node_toml, encode(request("submit", **submit_body())))
    assert done.returncode == 0, done.stderr
    job_id = json.loads(done.stdout)["body"]["job_id"]

    data = b"tar.gz bytes"
    digest = hashlib.sha256(data).hexdigest()
    done = mulebox(["rpc-upload", job_id, digest], node_toml, data)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["body"]["state"] == "queued"

    done = mulebox(["rpc"], node_toml, encode(request("status", job_id=job_id)))
    assert json.loads(done.stdout)["body"]["position"] == 1

    done = mulebox(["rpc-download", job_id], node_toml)
    assert done.returncode == 0 and done.stdout == data


def test_rpc_garbage_exits_4_without_traceback(node_toml):
    done = mulebox(["rpc"], node_toml, b"garbage\n")
    assert done.returncode == 4
    assert json.loads(done.stdout)["body"]["code"] == "bad_request"
    assert b"Traceback" not in done.stdout + done.stderr


def test_bad_node_config_exits_2(tmp_path):
    missing = tmp_path / "nope.toml"
    done = mulebox(["rpc"], missing)
    assert done.returncode == 2 and done.stdout == b""
