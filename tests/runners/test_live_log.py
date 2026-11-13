"""A runner job's steps and output, read from files laid out as the runner writes them."""

from mulebox.common.protocol import Message, MessageType
from mulebox.runners.live_log import RunnerLog
from mulebox.worker.link import request as make

JOB = "b75fcf21-8ea5-5571-9290-eee81c654533"
PLAN = "d20691f6-9c82-5b6a-b39b-8cea59a72f41"
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
    diary.write_text(f'    "planId": "{PLAN}",\n'
                     f"[x INFO JobRunner] Job ID {JOB}\n"
                     f"{STAMP} Processing step: DisplayName='First step'\n")
    page = diag / "pages" / f"{PLAN}_{RECORD}_1.log"
    page.write_bytes(b"")
    (diag / "pages" / f"{PLAN}_{JOB}_1.log").write_text("2026-11-07T09:32:41Z every step again\n")
    log = RunnerLog("job-1", folder, make)
    log.poll(0)
    assert sent_text(log) == "mulebox: step at 2026-11-07T09:32:11Z: First step\n"

    with open(diary, "a") as fh:
        fh.write(f"[x INFO JobServerQueue] Try to append 1 batches web console lines for record "
                 f"'{RECORD}', success rate: 1/1.\n")
    page.write_bytes("﻿2026-11-07T09:32:41.1Z ##[group]Run tests\n"
                     "2026-11-07T09:32:41.2Z first line\n"
                     "2026-11-07T09:32:41.3Z ##[endgroup]\n".encode())
    log.poll(0)
    page.unlink()  # GitHub has it: the runner deletes it, the open file still reads
    with open(diary, "a") as fh:
        fh.write(f"{STAMP} Step result: Failed\n"
                 "[2026-11-07 09:33:02Z INFO StepsRunner] Update job result with current step "
                 "result 'Failed'.\n")
    log.poll(0)
    assert sent_text(log) == ("--- output of First step\nRun tests\nfirst line\n"
                              "mulebox: step failed at 2026-11-07T09:33:02Z: First step\n")


def test_every_step_ends_with_its_result_and_time_as_the_diary_says(tmp_path):
    """Lines as a real runner wrote them (2.3xx): a passed, a skipped and a cancelled step."""
    folder, diag = runner(tmp_path)
    (diag / "Worker_20261111-072502-utc.log").write_text("\n".join([
        f'    "planId": "{PLAN}",',
        "[2026-11-11 07:25:03Z INFO StepsRunner] Processing step: DisplayName='Set up runner'",
        "[2026-11-11 07:26:33Z INFO StepsRunner] Step result: ",
        "[2026-11-11 07:26:33Z INFO StepsRunner] No need for updating job result with current "
        "step result 'Succeeded'.",
        "[2026-11-11 07:26:33Z INFO StepsRunner] Current state: job state = ''",
        "[2026-11-11 07:26:33Z INFO StepsRunner] Processing step: DisplayName='Post Run x'",
        "[2026-11-11 07:26:33Z INFO StepsRunner] Skipping step due to condition evaluation.",
        "[2026-11-11 07:26:33Z INFO StepsRunner] No need for updating job result with current "
        "step result 'Skipped'.",
        "[2026-11-11 07:26:33Z INFO StepsRunner] Processing step: DisplayName='count'",
        "[2026-11-11 07:31:17Z INFO StepsRunner] Step result: Canceled",
        "[2026-11-11 07:31:17Z INFO StepsRunner] No need for updating job result with current "
        "step result 'Canceled'.",
        "[2026-11-11 07:31:17Z INFO StepsRunner] Current state: job state = 'Canceled'", ""]))
    log = RunnerLog("job-1", folder, make)
    log.poll(0)
    assert sent_text(log) == (
        "mulebox: step at 2026-11-11T07:25:03Z: Set up runner\n"
        "mulebox: step passed at 2026-11-11T07:26:33Z: Set up runner\n"
        "mulebox: step at 2026-11-11T07:26:33Z: Post Run x\n"
        "mulebox: step skipped at 2026-11-11T07:26:33Z: Post Run x\n"
        "mulebox: step at 2026-11-11T07:26:33Z: count\n"
        "mulebox: step cancelled at 2026-11-11T07:31:17Z: count\n")


def test_pages_of_an_earlier_job_and_an_older_diary_are_left_alone(tmp_path):
    folder, diag = runner(tmp_path)
    (diag / "pages" / f"other-job_{RECORD}_1.log").write_text("2026-11-03T19:25:41Z old\n")
    old = diag / "Worker_20261103-192537-utc.log"
    old.write_text(f"{STAMP} Processing step: DisplayName='Old step'\n")
    log = RunnerLog("job-1", folder, make)
    log.poll(started_after=old.stat().st_mtime + 60)
    assert sent_text(log) == ""


def test_the_open_steps_cache_restore_is_read_at_the_times_the_runner_stamped(tmp_path):
    """Lines as the node's runner wrote them on 2026-11-12, restoring pip's cache over its VPN."""
    from mulebox.runners.live_log import stamp_time
    folder, diag = runner(tmp_path)
    diary = diag / "Worker_20261112-143740-utc.log"
    diary.write_text(f'    "planId": "{PLAN}",\n'
                     "[2026-11-12 14:38:06Z INFO StepsRunner] Processing step: "
                     "DisplayName='Run actions/setup-python@6d4fd22'\n"
                     f"[x INFO JobServerQueue] web console lines for record '{RECORD}'\n")
    page = diag / "pages" / f"{PLAN}_{RECORD}_1.log"
    page.write_bytes("﻿2026-11-12T14:38:20.1000000Z Cache hit for: setup-python-Linux-x64-"
                     "24.04-Ubuntu-python-3.13.18-pip-e3c887ed\n"
                     "2026-11-12T14:38:21.0000000Z Received 0 of 9806923 (0.0%), 0.0 MBs/sec\n"
                     "2026-11-12T14:40:21.0000000Z Received 1418315 of 9806923 (14.5%), "
                     "0.1 MBs/sec\n".encode())
    log = RunnerLog("job-1", folder, make)
    log.poll(0)
    at = stamp_time("2026-11-12T14:40:21.0000000Z x")
    assert at == stamp_time("﻿2026-11-12T14:40:21Z x") == 1794494421.0
    assert stamp_time("no stamp") is None
    found = log.download.reading(at + 30, cpu_pct=0.5)
    assert (found["name"], found["done_bytes"], found["total_bytes"]) == (
        "pip cache", 1418315, 9806923)
    assert found["step"] == "Run actions/setup-python@6d4fd22" and found["as_of_s"] == 30.0
    assert found["rate_bytes_s"] == round(1418315 / 120, 1) and found["stalled"] is False
    with open(diary, "a") as fh:
        fh.write("[2026-11-12 14:48:13Z INFO StepsRunner] No need for updating job result with "
                 "current step result 'Succeeded'.\n")
    log.poll(0)
    assert log.download.reading(at + 60) is None  # the step is over
