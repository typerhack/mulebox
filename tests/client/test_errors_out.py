"""Every error a command prints: its code, message and fix, and JSON with --json
(common/error_report.py; design.md, Errors with a code and a fix)."""

import json

from mulebox import cli
from mulebox.client import commands
from mulebox.client.remote import refusal
from mulebox.common import error_codes
from mulebox.common.errors import MuleboxError


def lines(text):
    return [ln for ln in text.splitlines() if ln.startswith("mulebox: ")]


def test_a_missing_config_says_its_code_and_fix(fake, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["check"]) == 2
    err = lines(capsys.readouterr().err)
    assert err[0].startswith("mulebox: error [config.missing]: ")
    assert err[1] == f"mulebox: fix: {error_codes.fix_for('config.missing')}"


def test_an_older_nodes_refusal_reads_as_its_wire_code(fake, capsys):
    fake.scenario(error="not_found")
    assert cli.main(["status", "job-01H0000000000000000000000"]) == 4
    err = lines(capsys.readouterr().err)
    assert "[request.not_found]" in err[0] and "scripted failure" in err[0]
    assert err[1].startswith("mulebox: fix: ")


def test_json_puts_the_error_on_stdout_too(fake, capsys):
    fake.scenario(error="no_worker")
    assert cli.main(["projects", "--json"]) == 4
    out, err = capsys.readouterr()
    found = json.loads(out)["error"]
    assert found["code"] == "job.no_node" and found["exit"] == 4
    assert found["fix"] == error_codes.fix_for("job.no_node")
    assert "[job.no_node]" in err


def test_a_reply_with_its_own_code_and_fix_keeps_them():
    exc = refusal({"code": "not_found", "message": "no job x", "error_code": "job.not_found",
                   "fix": "`mulebox queue`"})
    assert (exc.code, exc.error_code, exc.fix) == ("not_found", "job.not_found", "`mulebox queue`")
    unknown = refusal({"code": "conflict", "message": "m", "error_code": "made.up"})
    assert unknown.error_code == "request.conflict" and unknown.fix is None


def test_a_raise_may_name_a_closer_fix(capsys):
    def handler(args):
        raise commands.UsageError("no job 'x'", fix="`mulebox contract` lists the jobs")
    assert commands.guarded(handler)(None) == 2
    err = lines(capsys.readouterr().err)
    assert err == ["mulebox: error [usage.invalid]: no job 'x'",
                   "mulebox: fix: `mulebox contract` lists the jobs"]


def test_an_unexpected_error_is_internal_with_a_way_to_report_it(capsys, monkeypatch):
    monkeypatch.delenv("MULEBOX_DEBUG", raising=False)
    def handler(args):
        raise KeyError("boom")
    assert commands.guarded(handler)(None) == 1
    err = lines(capsys.readouterr().err)
    assert err[0] == "mulebox: error [mulebox.internal]: KeyError: 'boom'"
    assert "mulebox feedback guide" in err[1]


def test_a_mulebox_error_of_no_known_kind_keeps_its_code(capsys):
    def handler(args):
        raise MuleboxError("gone", error_code="node.too_old")
    assert commands.guarded(handler)(None) == 1
    assert "[node.too_old]" in capsys.readouterr().err


def test_secrets_are_redacted_in_message_and_fix(capsys):
    def handler(args):
        raise commands.UsageError("token ghp_" + "a" * 36, fix="use ghp_" + "b" * 36)
    commands.guarded(handler)(None)
    assert "ghp_aaaa" not in capsys.readouterr().err
