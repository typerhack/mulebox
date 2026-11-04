"""End to end through `mulebox.cli.main` with the scripted fake coordinator over fake ssh."""

import io
import tarfile

import pytest

from mulebox import cli

JOB = "job-01JC3X0000000000000000ABCD"


@pytest.fixture
def in_repo(make_repo, monkeypatch):
    repo = make_repo(tracked={"src/a.py": "x = 1\n", ".env": "SECRET=1\n"})
    monkeypatch.chdir(repo / "src")  # the project root is found by walking up
    return repo


def test_check_passes_end_to_end(fake, in_repo, capsys):
    fake.scenario(log=["building\n", "ok\n"])
    assert cli.main(["check"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "building\nok\n"
    assert f"mulebox: job {JOB} passed in 12s" in captured.err
    with tarfile.open(fileobj=io.BytesIO(fake.upload())) as tar:
        names = set(tar.getnames())
    assert names == {".mulebox.yml", "src/a.py"}
    submit = fake.requests()[0]
    assert submit["type"] == "submit" and submit["body"]["argv"] == ["bash", "-e", "-c", "echo ok"]


def test_failed_job_returns_its_exit_code(fake, in_repo, capsys):
    fake.scenario(log=["boom\n"], outcome="failed", exit_code=3)
    assert cli.main(["check", "test"]) == 3
    assert "failed (exit 3)" in capsys.readouterr().err


def test_watch_drop_reconnects(fake, in_repo, capsys, monkeypatch):
    from mulebox.client import submit

    monkeypatch.setattr(submit, "WATCH_RETRY_DELAY_S", 0)
    fake.scenario(log=["one\n", "two\n"], drop_watch_once=True)
    assert cli.main(["check"]) == 0
    assert capsys.readouterr().out == "one\ntwo\n"
    watches = [r for r in fake.requests() if r["type"] == "watch"]
    assert [w["body"]["offset"] for w in watches] == [0, 4]


def test_unreachable_exits_3_and_never_suggests_local(fake, in_repo, capsys):
    fake.scenario(down=True)
    assert cli.main(["check"]) == 3
    err = capsys.readouterr().err
    assert "unreachable" in err and "locally" not in err.lower()


def test_coordinator_error_exits_4(fake, in_repo, capsys):
    fake.scenario(error="internal")
    assert cli.main(["check"]) == 4
    assert "scripted failure" in capsys.readouterr().err


def test_unknown_job_exits_2(fake, in_repo, capsys):
    assert cli.main(["check", "nope"]) == 2
    assert "no job 'nope'" in capsys.readouterr().err
    assert fake.requests() == []


def test_run_needs_a_command(fake, in_repo, capsys):
    assert cli.main(["run"]) == 2
    assert cli.main(["run", "--"]) == 2


def test_run_sends_argv(fake, in_repo, capsys):
    fake.scenario(log=["t\n"])
    assert cli.main(["run", "--", "pytest", "-k", "a b"]) == 0
    assert fake.requests()[0]["body"]["argv"] == ["pytest", "-k", "a b"]


def test_no_project_config_exits_2(fake, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["check"]) == 2
    assert ".mulebox.yml" in capsys.readouterr().err


def test_queue_prints_a_plain_table(fake, capsys):
    fake.scenario(jobs=[{"job_id": JOB, "project": "example-app", "job": "check",
                         "branch": "main", "state": "queued", "position": 1,
                         "created_at": 1.0}])
    assert cli.main(["queue"]) == 0
    out = capsys.readouterr().out
    assert JOB in out and "Queued (1)" in out
    assert fake.requests()[0]["body"] == {"limit": 20}


def test_logs_and_cancel(fake, capsys):
    fake.scenario(log=["line 1\n", "line 2\n"])
    assert cli.main(["logs", JOB]) == 0
    assert capsys.readouterr().out == "line 1\nline 2\n"
    assert cli.main(["logs", JOB, "-f"]) == 0
    assert capsys.readouterr().out == "line 1\nline 2\n"
    watch = [r for r in fake.requests() if r["type"] == "watch"][0]
    assert watch["body"]["lease"] is False
    assert cli.main(["cancel", JOB]) == 0
    assert f"cancel requested for job {JOB}" in capsys.readouterr().err
