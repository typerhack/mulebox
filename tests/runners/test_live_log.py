"""A runner job's steps and output, read from files laid out as the runner writes them."""

from mulebox.common.protocol import Message, MessageType
from mulebox.runners.live_log import RunnerLog
from mulebox.worker.link import request as make

GH_JOB = "d20691f6-9c82-5b6a-b39b-8cea59a72f41"
RECORD = "1d474f7c-0a18-43e9-9ad8-57d8d0598a92"
STAMP = "[2026-11-07 09:32:11Z INFO StepsRunner]"


def sent_text(log):
    chunks = []
    log.send(lambda msg: chunks.append(msg) or Message(MessageType.STATUS_OK, "r", {"job_id": "job-1", "state": "running"}))
    return "".join(m.body["data"] for m in chunks if m.type is MessageType.LOG_CHUNK)


def runner(tmp_path):
    diag = tmp_path / "runner" / "_diag"
    (diag / "pages").mkdir(parents=True)
    return tmp_path / "runner", diag


def test_steps_live_and_a_step_output_under_its_name_even_after_the_page_is_deleted(tmp_path):
    folder, diag = runner(tmp_path)
    diary = diag / "Worker_20261107-093210-utc.log"
    diary.write_text(f"[x INFO JobRunner] Job ID {GH_JOB}\n"
                     f"{STAMP} Processing step: DisplayName='First step'\n")
    page = diag / "pages" / f"{GH_JOB}_{RECORD}_1.log"
    page.write_bytes(b"")
    log = RunnerLog("job-1", folder, make)
    log.poll(0)
    assert sent_text(log) == "mulebox: step: First step\n"

    with open(diary, "a") as fh:
        fh.write(f"[x INFO JobServerQueue] Try to append 1 batches web console lines for record "
                 f"'{RECORD}', success rate: 1/1.\n")
    page.write_bytes("﻿2026-11-07T09:32:41.1Z ##[group]Run tests\n"
                     "2026-11-07T09:32:41.2Z first line\n"
                     "2026-11-07T09:32:41.3Z ##[endgroup]\n".encode())
    log.poll(0)
    page.unlink()  # GitHub has it: the runner deletes it, the open file still reads
    with open(diary, "a") as fh:
        fh.write(f"{STAMP} Step result: Failed\n")
    log.poll(0)
    assert sent_text(log) == ("--- output of First step\nRun tests\nfirst line\n"
                              "mulebox: step failed: First step\n")


def test_pages_of_an_earlier_job_and_an_older_diary_are_left_alone(tmp_path):
    folder, diag = runner(tmp_path)
    (diag / "pages" / f"other-job_{RECORD}_1.log").write_text("2026-11-03T19:25:41Z old\n")
    old = diag / "Worker_20261103-192537-utc.log"
    old.write_text(f"{STAMP} Processing step: DisplayName='Old step'\n")
    log = RunnerLog("job-1", folder, make)
    log.poll(started_after=old.stat().st_mtime + 60)
    assert sent_text(log) == ""
