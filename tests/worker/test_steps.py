"""Stages of a job: the marks in its script, the rows they make, and how those travel."""

import subprocess

import pytest

from mulebox.common.protocol import MessageType, Outcome
from mulebox.common import status
from mulebox.worker import jobspec, steps
from mulebox.worker.logtail import LogTailer
from mulebox.worker.link import LinkError, request
from mulebox.worker.steps import StepTracker

from .test_agent import agent, clock, executor, cleaned, run_until, submit  # noqa: F401
from .test_agent_compose import agent as compose_agent  # noqa: F401
from .test_agent_compose import daemon, finished, stand_in  # noqa: F401
from .test_agent_compose import submit as submit_compose


def mark(tracker, at, stage):
    return f"::mulebox-step:{tracker.marker}:{at}:{stage}\n"


def stages(link):
    rows = {}
    for msg in link.of_type(MessageType.STEPS):
        rows |= {row["seq"]: row for row in msg.body["steps"]}
    return [rows[seq] for seq in sorted(rows)]


def test_a_mark_starts_a_stage_and_leaves_the_log():
    tracker = StepTracker()
    tracker.begin("prepare", 100.0)
    assert tracker.line(mark(tracker, 105.5, "setup")) == ""
    rows = tracker.pending()
    assert [(r["stage"], r["started_at"], r["finished_at"], r["exit_code"]) for r in rows] == [
        ("prepare", 100.0, 105.5, 0), ("setup", 105.5, None, None)]


def test_a_comma_in_the_time_is_read_too():
    tracker = StepTracker()
    tracker.line(mark(tracker, "105,5", "setup"))
    assert tracker.pending()[0]["started_at"] == 105.5


def test_output_without_a_line_break_before_a_mark_stays():
    tracker = StepTracker()
    assert tracker.line("progress" + mark(tracker, 1, "setup")) == "progress\n"


def test_a_mark_inside_a_line_is_plain_output_and_loses_nothing():
    tracker = StepTracker()
    line = f"seen {mark(tracker, 1, 'setup').strip()} and more\n"
    assert tracker.line(line) == line
    assert tracker.pending() == []


def test_a_mark_from_another_job_is_plain_output():
    tracker, other = StepTracker(), StepTracker()
    line = mark(other, 1, "setup")
    assert tracker.line(line) == line
    assert tracker.pending() == []


def test_an_unknown_stage_makes_no_row():
    tracker = StepTracker()
    assert tracker.line(mark(tracker, 1, "nonsense")) == ""
    assert tracker.pending() == []


def test_the_last_line_of_a_failed_stage_is_kept():
    tracker = StepTracker()
    tracker.begin("command", 1.0)
    for line in ("compiling\n", "error TS2322: bad type\n", "\n"):
        tracker.line(line)
    tracker.close(2, 9.0, failed=True)
    row = tracker.pending()[0]
    assert row["exit_code"] == 2 and row["failing_line"] == "error TS2322: bad type"


def test_a_stage_that_passed_or_was_cancelled_has_no_failing_line():
    tracker = StepTracker()
    tracker.begin("setup", 1.0)
    tracker.line("fine\n")
    tracker.begin("command", 2.0)
    tracker.line("still running\n")
    tracker.close(None, 3.0, failed=False)
    assert [row["failing_line"] for row in tracker.pending()] == [None, None]


def test_a_failing_line_is_cut():
    tracker = StepTracker()
    tracker.begin("command", 1.0)
    tracker.line("x" * 5000 + "\n")
    tracker.close(1, 2.0, failed=True)
    assert len(tracker.pending()[0]["failing_line"]) == status.MAX_FAILING_LINE


def test_the_report_on_containers_is_not_part_of_the_stage():
    tracker = StepTracker()
    tracker.begin("services", 1.0)
    tracker.line("container exited (1)\n")
    tracker.line(mark(tracker, 5, "end"))
    tracker.line("mulebox: the job failed; the state and last log lines of its containers:\n")
    tracker.close(1, 9.0, failed=True)
    row = tracker.pending()[0]
    assert row["finished_at"] == 5 and row["failing_line"] == "container exited (1)"


def test_a_time_before_the_start_never_gives_a_negative_stage():
    tracker = StepTracker()
    tracker.begin("prepare", 100.0)
    tracker.close(0, 50.0, failed=False)
    assert tracker.pending()[0]["finished_at"] == 100.0


def test_sent_rows_are_not_sent_again_until_they_change():
    tracker = StepTracker()
    tracker.begin("setup", 1.0)
    tracker.sent()
    assert tracker.pending() == []
    tracker.close(0, 2.0, failed=False)
    assert tracker.pending()[0]["finished_at"] == 2.0


def run_script(tmp_path, setup, argv):
    tracker = StepTracker()
    script = jobspec.build_script(setup, argv, (), tracker.marker)
    done = subprocess.run(["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True)
    kept = "".join(tracker.line(line) for line in done.stdout.splitlines(keepends=True))
    return done, tracker, kept


def test_the_script_marks_its_stages_and_the_result_is_the_jobs(tmp_path):
    done, tracker, kept = run_script(tmp_path, "echo set up", ["bash", "-c", "exit 7"])
    assert done.returncode == 7 and kept == "set up\n"
    assert [row["stage"] for row in tracker.pending()] == ["setup", "command"]


def test_the_script_has_nothing_systemd_would_expand():
    assert "${" not in steps.shell_function("abc")
    assert "$$" not in steps.shell_function("abc")


def test_a_plain_script_has_no_marks():
    assert "mulebox_step" not in jobspec.build_script("a", ["b"])


# Through the tailer


def tailer(tmp_path, tracker):
    return LogTailer(tmp_path / "out.log", "job-1", "att-1", request, steps=tracker)


def test_marks_never_reach_the_stored_log_and_rows_are_redacted(tmp_path):
    tracker = StepTracker()
    tail = tailer(tmp_path, tracker)
    (tmp_path / "out.log").write_text(
        f"before\n{mark(tracker, 1, 'command')}password=hunter2hunter2\n")
    tail.read_new()
    tail.finish()
    tracker.close(1, 2.0, failed=True)
    sent = []

    def record(msg):
        sent.append(msg)
        return msg

    tail.send(record)
    logged = "".join(m.body["data"] for m in sent if m.type is MessageType.LOG_CHUNK)
    assert logged == "before\npassword=[redacted]\n"
    rows = next(m for m in sent if m.type is MessageType.STEPS).body["steps"]
    assert rows[-1]["failing_line"] == "password=[redacted]"


def test_a_line_arriving_in_pieces_is_one_line(tmp_path):
    tracker = StepTracker()
    tail = tailer(tmp_path, tracker)
    text = mark(tracker, 1, "command")
    tail._take(text[:10])
    tail._take(text[10:])
    assert [row["stage"] for row in tracker.pending()] == ["command"]


def test_a_very_long_line_is_not_held_back(tmp_path):
    tail = tailer(tmp_path, StepTracker())
    tail._take("x" * 100_000)
    assert sum(len(piece) for _, piece in tail._queue) == 100_000


def test_a_failed_send_keeps_the_rows_and_an_error_reply_drops_them(tmp_path):
    tracker = StepTracker()
    tracker.begin("prepare", 1.0)
    tail = tailer(tmp_path, tracker)

    def down(msg):
        raise LinkError("down")

    with pytest.raises(LinkError):
        tail.send(down)
    assert tracker.pending()
    tail.send(lambda msg: request(MessageType.ERROR, code="bad_request", message="no"))
    assert tracker.pending() == []


# Through the agent


def test_a_plain_job_reports_every_stage(agent, fake_link):
    submit(fake_link, "bash", "-c", "echo hi", setup="true")
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    rows = stages(fake_link)
    assert [row["stage"] for row in rows] == ["prepare", "environment", "setup", "command",
                                              "cleanup"]
    assert all(row["finished_at"] is not None for row in rows)
    assert {row["exit_code"] for row in rows} == {0}


def test_rows_reach_the_coordinator_before_the_result(agent, fake_link):
    submit(fake_link, "true")
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    kinds = [m.type for m in fake_link.sent]
    assert max(i for i, kind in enumerate(kinds) if kind is MessageType.STEPS) < kinds.index(
        MessageType.RESULT)


def test_a_failed_command_says_where_and_why(agent, fake_link):
    submit(fake_link, "bash", "-c", "echo boom; exit 3")
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    failed = status.failed_step(stages(fake_link))
    assert failed["stage"] == "command" and failed["exit_code"] == 3
    assert failed["failing_line"] == "boom"


def test_a_job_that_cannot_start_fails_in_environment(agent, fake_link):
    def offline(paths, name, version):
        raise OSError("no route")

    agent.install_toolchain = offline
    submit(fake_link, "true", toolchain={"node": "1.2.3"})
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    failed = status.failed_step(stages(fake_link))
    assert failed["stage"] == "environment" and "not installed" in failed["failing_line"]


def test_a_compose_job_has_images_and_services(compose_agent, fake_link):
    submit_compose(fake_link, "echo ran", setup="true")
    run_until(compose_agent, finished(fake_link))
    assert [row["stage"] for row in stages(fake_link)] == [
        "prepare", "environment", "images", "services", "setup", "command", "cleanup"]


def test_the_rows_of_a_failed_start_name_the_services_stage(
        compose_agent, fake_link, tmp_path):
    (tmp_path / "up-fails").touch()
    (tmp_path / "up-prints").write_text("dependency failed to start\n")
    submit_compose(fake_link, "echo ran")
    run_until(compose_agent, finished(fake_link))
    failed = status.failed_step(stages(fake_link))
    assert failed["stage"] == "services" and failed["exit_code"] == 9
    assert failed["failing_line"] == "dependency failed to start"


def test_outcomes_that_keep_a_failing_line():
    from mulebox.worker.job import ended_badly

    assert ended_badly(Outcome.TIMED_OUT) and ended_badly(Outcome.FAILED)
    assert not ended_badly(Outcome.CANCELLED) and not ended_badly(Outcome.INTERRUPTED)
