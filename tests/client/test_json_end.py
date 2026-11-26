"""`--json` on commands that print as they go: output on stderr, one object on stdout."""

import argparse
import json

from mulebox.client import attention, json_end
from mulebox.client.commands import UsageError, guarded


def parsed(json_flag=True):
    parser = argparse.ArgumentParser()
    json_end.add(parser)
    return parser.parse_args(["--json"] if json_flag else [])


def test_output_goes_to_stderr_and_one_object_to_stdout(capsys):
    def handler(args):
        print("log line")
        json_end.record(job_id="job-1", outcome="passed", missing=None)
        attention.tell({"finished_away": [{"job_id": "job-0", "kind": "job", "project": "example-app",
                                           "job": "check", "outcome": "failed",
                                           "exit_code": 1}]}, __import__("sys").stderr)
        return 7

    assert guarded(handler)(parsed()) == 7
    out, err = capsys.readouterr()
    end = json.loads(out)
    assert end["exit"] == 7 and end["job_id"] == "job-1" and "missing" not in end
    notice = end["notices"][0]
    assert notice["kind"] == "finished_away" and notice["data"]["job_id"] == "job-0"
    assert "finished while you were away" in notice["text"]
    assert "log line" in err and "log line" not in out


def test_an_error_is_the_error_object_alone(capsys):
    def handler(args):
        print("half way")
        raise UsageError("no job 'x'")

    assert guarded(handler)(parsed()) == 2
    out, err = capsys.readouterr()
    assert json.loads(out)["error"]["code"] == "usage.invalid"
    assert "half way" in err


def test_without_json_nothing_changes(capsys):
    def handler(args):
        print("log line")
        json_end.record(job_id="job-1")
        return 0

    assert guarded(handler)(parsed(json_flag=False)) == 0
    assert capsys.readouterr().out == "log line\n"
