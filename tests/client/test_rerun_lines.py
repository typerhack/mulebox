"""`mulebox check --from-stage`: what the client sends and says (rerun_lines.py)."""

import io
import time

import pytest

from mulebox.client import github_status, rerun_lines, summary
from mulebox.client.submit import run_job
from mulebox.common.protocol import MessageType

from .test_submit import JOB, PROJECT, FakeRemote, msg, result, streams


class RerunRemote(FakeRemote):
    def __init__(self, streams, rerun):
        super().__init__(streams)
        self.rerun = rerun

    def call(self, m):
        if m.type is MessageType.SUBMIT:
            self.calls.append(m)
            body = {"job_id": JOB, "state": "uploading"}
            return msg("submit_ok", **body, **({"rerun": self.rerun} if self.rerun else {}))
        return super().call(m)


def submitted(make_repo, rerun, stage="command"):
    remote, io_ = RerunRemote([[result()]], rerun), streams()
    assert run_job(PROJECT, "check", make_repo(), remote, io_, from_stage=stage) == 0
    return remote.calls[0].body, io_.err.getvalue()


def test_the_stage_is_sent_and_the_earlier_result_is_not_asked_for(make_repo):
    body, _ = submitted(make_repo, {"from_stage": "command", "reuses": "job-x", "node": "build-1"})
    assert body["from_stage"] == "command" and "reuse" not in body


def test_a_rerun_says_whose_containers_it_uses(make_repo):
    _, err = submitted(make_repo, {"from_stage": "setup", "reuses": "job-x", "node": "build-1"},
                       "setup")
    assert "rerun from setup in the containers of job-x, kept on build-1" in err


def test_nothing_kept_says_why(make_repo):
    _, err = submitted(make_repo, {"from_stage": "command", "note": "no failed job is kept"})
    assert "mulebox: no failed job is kept" in err


def test_an_older_node_says_it_runs_from_the_start(make_repo):
    _, err = submitted(make_repo, None)
    assert "cannot rerun from a stage (it is older than 1.46)" in err


def test_a_plain_check_says_nothing_about_reruns():
    assert rerun_lines.submitted({"rerun": {"note": "x"}}, None) is None


@pytest.mark.parametrize("job, stage, command", [
    ("check", "command", "mulebox check --from-stage command"),
    ("test", "setup", "mulebox check test --from-stage setup"),
    ("run", "install", "mulebox run --from-stage install -- <command>"),
    ("check", "services", "mulebox check --from-stage command"),  # failed before: the command
])
def test_a_kept_failure_names_the_rerun_command(job, stage, command):
    lines = rerun_lines.kept_lines(job, {"kept_until": 1000.0 + 14.6 * 60, "kept_on": "build-1",
                                         "stage": stage}, now=1000.0)
    assert lines == [f"its containers are kept on build-1 for 15 min: after a fix, `{command}` "
                     f"reruns it from {command.split('--from-stage ')[1].split()[0]}, with no "
                     "new images, services or stages before it"]


def test_the_summary_carries_it_after_the_outcome():
    out = summary.render(JOB, {"outcome": "failed", "exit_code": 7, "job": "check",
                               "kept_until": time.time() + 600}, ["boom"])
    assert out[1].startswith("outcome:") and out[2].startswith("its containers are kept for 10")
    assert summary.render(JOB, {"outcome": "failed", "exit_code": 7}, ["boom"])[2:3] == [
        "last lines of the log, without progress and container logs "
        f"(full log: mulebox logs {JOB}):"]


def test_no_github_status_for_a_rerun(tmp_path):
    out, ran = io.StringIO(), []
    project = PROJECT.__class__(**{**PROJECT.__dict__, "github_status": True})
    code = github_status.around(project, tmp_path, "check", False, out, lambda: 0,
                                run=lambda *a, **k: ran.append(a), rerun=True)
    assert code == 0 and not ran and "no GitHub status with --from-stage" in out.getvalue()
