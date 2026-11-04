"""What a finished job reads like through the real client and the real coordinator code."""

import json
import time

from mulebox import cli
from mulebox.client import report
from mulebox.common import config
from mulebox.coordinator import retention

from .test_detached import FakeWorker, detach

FAILED_SETUP = ({"seq": 0, "stage": "prepare", "started_at": 1.0, "finished_at": 2.0, "exit_code": 0},
                {"seq": 1, "stage": "setup", "started_at": 2.0, "finished_at": 3.0, "exit_code": 3,
                 "failing_line": "boom"})


def test_the_summary_and_events_show_the_stage_that_really_failed(local, in_project, capsys):
    job_id, _ = detach(capsys)
    FakeWorker(local.store, local.staging, steps=FAILED_SETUP).run_next()
    assert cli.main(["wait", job_id]) == 3
    assert "failed stage: setup" in capsys.readouterr().err
    assert cli.main(["logs", job_id, "--summary"]) == 0
    assert "failed stage: setup" in capsys.readouterr().out
    assert cli.main(["events", "--job", job_id, "--json"]) == 3
    finished = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [event["stage"] for event in finished] == ["setup"]  # one final line, not two
    assert cli.main(["events", "--job", job_id]) == 3
    assert "failed stage setup" in capsys.readouterr().out


def test_status_lists_stages_beside_what_is_usual(local, in_project, capsys):
    rows = ({"seq": 0, "stage": "command", "started_at": 1.0, "finished_at": 31.0, "exit_code": 0},)
    job_id, _ = detach(capsys)
    FakeWorker(local.store, local.staging, exit_code=0, steps=rows).run_next()
    assert cli.main(["status", job_id]) == 0
    out = capsys.readouterr().out
    assert "  command: 30s (usual 30s)\n" in out and "usual for this job: 30s (1 past runs)" in out
    assert "%" not in out


def test_a_log_really_removed_by_retention_reads_as_expired(local, in_project, capsys):
    job_id, _ = detach(capsys)
    FakeWorker(local.store, local.staging).run_next()
    log_days, step_days = config.DEFAULT_LOG_DAYS, config.DEFAULT_STEP_DAYS
    soon = time.time() + (log_days - 1) * retention.DAY_S
    assert retention.sweep(local.store, local.staging, soon, log_days, step_days) == (0, 0)
    later = time.time() + (log_days + 1) * retention.DAY_S
    assert retention.sweep(local.store, local.staging, later, log_days, step_days)[0] == 1
    assert not local.staging.log_path(job_id).exists()
    assert cli.main(["logs", job_id]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert report.expired_line(job_id) in captured.err and f"{log_days} days" in captured.err
    assert cli.main(["logs", job_id, "--summary"]) == 0
    captured = capsys.readouterr()
    assert "has expired" in captured.err and "exit code 3" in captured.out
    assert cli.main(["wait", job_id]) == 3  # the job and its result stay
    assert cli.main(["status", job_id]) == 0
