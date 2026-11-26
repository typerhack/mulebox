"""`mulebox queue --json`: the coordinator's queue reply, as is, on stdout."""

import json

from mulebox.client import commands
from mulebox.cli import build_parser


class Reply:
    body = {"jobs": [{"job_id": "job-1", "state": "queued", "position": 1,
                      "waiting_for": "the machines are busy with 1 job"}]}


class Remote:
    target = "build-1"

    def call(self, _):
        return Reply()


def test_queue_json_prints_every_job_with_its_reason(monkeypatch, capsys):
    monkeypatch.setattr(commands, "connect", lambda: Remote())
    args = build_parser().parse_args(["queue", "--json"])
    assert args.func(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["jobs"][0]["waiting_for"] == "the machines are busy with 1 job"
