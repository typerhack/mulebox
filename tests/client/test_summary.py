"""The failure summary: what stays, what is noise, and the end-to-end lines."""

import pytest

from mulebox import cli
from mulebox.client import summary
from mulebox.client.summary import LogTail
from mulebox.common.status import CONTAINER_LOGS_NOTE, NOT_STARTED_NOTE

JOB = "job-01JC3X0000000000000000ABCD"


def lines_of(text, **kwargs):
    tail = LogTail(**kwargs)
    tail.feed(text)
    return summary.relevant_lines(tail)


def test_keeps_the_end_of_the_log():
    text = "".join(f"step {i} done differently {'x' * i}\n" for i in range(40))
    assert lines_of(text) == [line for line in text.splitlines()[-20:]]


def test_the_failure_stays_when_its_stack_and_totals_fill_the_last_lines():
    head = ["TAP version 13", "# Subtest: top order", "not ok 1 - top order",
            "  duration_ms: 112", "  failureType: 'testCodeFailure'", "  error: |-",
            "    ranking differs", "  code: 'ERR_ASSERTION'", "  name: 'AssertionError'"]
    rest = [f"  frame {chr(97 + i)} of the stack" for i in range(12)]
    rest += [f"# {word} 1" for word in ("tests", "suites", "pass", "fail", "cancelled",
                                        "skipped", "todo", "duration_ms")]
    shown = lines_of("\n".join(head + rest) + "\n")
    at = shown.index(summary.SKIPPED)
    assert shown[:at] == ["not ok 1 - top order", "  error: |-", "    ranking differs"]
    assert shown[at + 1:] == rest


def test_earlier_failures_are_capped_at_the_first():
    text = "".join(f"FAIL test {chr(97 + i)}\n" for i in range(20))
    text += "".join(f"line {chr(97 + i)} of the rest\n" for i in range(26))
    shown = lines_of(text)
    assert shown[0] == "FAIL test a" and len(shown) == summary.MAX_EARLIER + 1 + 20


def test_a_gate_with_two_failed_parts_shows_both():
    """A real gate's shape: a type error first, then hundreds of lines ending in a failed test."""
    log = ("check: lint passed (5s)\n"
           "check: types FAILED (75s) - last lines of types.log:\n"
           "lib/env.ts(109,14): error TS2322: Type 'string' is not assignable to type 'number'.\n"
           "check: test FAILED (178s) - last lines of test.log:\n"
           + "".join(f" ok tests/unit/case-{i}-{'x' * (i % 7)}.test.ts\n" for i in range(300))
           + " FAIL tests/unit/env.test.ts\nAssertionError: expected 2 to be 3\n")
    lines = lines_of(log)
    assert any("error TS2322" in line for line in lines)
    assert sum("FAILED" in line for line in lines) == 2


def test_forty_errors_in_one_part_do_not_hide_another_part():
    errors = "".join(f"src/a{i}.ts(1,1): error TS2322: wrong\n" for i in range(40))
    log = f"check: types FAILED\n{errors}check: test FAILED\n"
    log += "".join(f"line {'y' * i}\n" for i in range(30))
    lines = lines_of(log)
    assert "check: test FAILED" in lines and "check: types FAILED" in lines


@pytest.mark.parametrize("line", [
    "src/main.c:12:5: error: expected ';'", "  10:5  error  'x' is not defined  no-undef",
    "a.ts(1,2): error TS1005: ';' expected."])
def test_compiler_and_lint_errors_read_as_the_failure(line):
    lines = lines_of(line + "\n" + "".join(f"{'z' * i} done\n" for i in range(30)))
    assert line in lines


def test_a_quiet_log_has_no_earlier_lines():
    text = "".join(f"step {chr(97 + i)}\n" for i in range(26))
    assert summary.SKIPPED not in lines_of(text)


def test_container_logs_are_left_out():
    text = f"src/a.ts(3,1): error TS2322\n{CONTAINER_LOGS_NOTE}\nNAME  STATE\napi-1 | boom\n"
    assert lines_of(text) == ["src/a.ts(3,1): error TS2322"]


def test_the_workers_last_word_stays_after_container_logs():
    text = f"Error: dial tcp\n{CONTAINER_LOGS_NOTE}\ndb | noise\n{NOT_STARTED_NOTE} no image\n"
    assert lines_of(text) == ["Error: dial tcp", f"{NOT_STARTED_NOTE} no image"]


def test_a_lost_connection_at_the_end_gets_a_hint():
    out = summary.render(JOB, {"outcome": "failed", "exit_code": 1},
                         ["npm ERR! code ECONNRESET", "npm ERR! network request failed"])
    assert any("reads like a network failure" in line for line in out)


def test_a_service_refusing_or_an_old_timeout_gets_no_hint():
    lines = ["ETIMEDOUT, retrying", *(f"test {n} ok" for n in range(summary.HINT_LINES)),
             "Error: connect ECONNREFUSED 127.0.0.1:5432"]
    out = summary.render(JOB, {"outcome": "failed", "exit_code": 1}, lines)
    assert not any("reads like a network failure" in line for line in out)


def test_progress_is_left_out_but_numbers_in_results_are_not():
    text = ("Progress: resolved 543, reused 500, downloaded 0, added 0\n"
            "  45% building\n[=====>     ] 12/40\n12MB/40MB\n"
            "Downloading example-1.0.whl (12 kB)\n"
            "0123456789ab: Pull complete\n"
            " Container example-api-1  Started\n"
            " ✔ Network example_default  Created\n"
            "Tests  3 failed | 9 passed\n"
            "Coverage 45% is below the 90% threshold\n")
    assert lines_of(text) == ["Tests  3 failed | 9 passed",
                              "Coverage 45% is below the 90% threshold"]


def test_text_a_terminal_overwrites_and_colour_are_gone():
    assert lines_of("working 1\rworking 2\rFAILED\r\n\x1b[31mred\x1b[0m\n") == ["FAILED", "red"]


def test_a_run_of_similar_lines_keeps_the_last_with_a_count():
    text = "".join(f"retry {i} of 9\n" for i in range(1, 6)) + "gave up\n"
    assert lines_of(text) == ["retry 5 of 9 (and 4 like it)", "gave up"]


def test_two_similar_lines_both_stay():
    assert lines_of("fail test 1\nfail test 2\n") == ["fail test 1", "fail test 2"]


def test_a_tail_never_shows_half_a_line():
    tail = LogTail(keep=10)
    tail.feed("a very long first line\nshort\n")
    assert tail.cut and summary.relevant_lines(tail) == ["short"]


def test_very_long_lines_are_cut_and_control_characters_replaced():
    assert lines_of("x" * 500 + "\n")[0] == "x" * summary.MAX_WIDTH
    assert lines_of("bell\x07\n") == ["bell?"]


def test_only_failures_get_a_summary():
    assert summary.wanted({"outcome": "failed"}) and summary.wanted({"outcome": "timed_out"})
    assert summary.wanted({"outcome": "interrupted"})
    assert not summary.wanted({"outcome": "passed"})
    assert not summary.wanted({"outcome": "cancelled"})


def test_render_names_outcome_and_exit_code():
    text = summary.render(JOB, {"outcome": "failed", "exit_code": 2}, ["boom"])
    assert text[1] == "outcome: failed, exit code 2"
    assert text[-1] == "| boom" and f"mulebox logs {JOB}" in text[2]


def test_render_uses_the_stage_the_result_gives():
    text = summary.render(JOB, {"outcome": "failed", "exit_code": 1, "stage": "setup"}, [])
    assert "failed stage: setup" in text
    assert "the log has nothing else to show" in text


def test_render_knows_a_job_that_never_started():
    line = f"{NOT_STARTED_NOTE} toolchain node 22.22.3 is not installed"
    text = summary.render(JOB, {"outcome": "failed"}, [line])
    assert "failed stage: start" in text and "outcome: failed, exit code 5" in text


def test_the_exit_code_shown_is_what_the_command_returns():
    assert "exit code 124" in summary.render(JOB, {"outcome": "timed_out"}, [])[1]
    assert "exit code 75" in summary.render(JOB, {"outcome": "interrupted"}, [])[1]


def test_check_ends_with_the_summary_on_stderr(fake, make_repo, monkeypatch, capsys):
    monkeypatch.chdir(make_repo())
    fake.scenario(log=["Progress: resolved 1\n", "boom\n"], outcome="failed", exit_code=3)
    assert cli.main(["check", "test"]) == 3
    captured = capsys.readouterr()
    assert captured.out == "Progress: resolved 1\nboom\n"  # the log itself is untouched
    assert f"mulebox: failure summary of job {JOB}\n" in captured.err
    assert "mulebox: | boom\n" in captured.err and "| Progress" not in captured.err


def test_a_passing_check_prints_no_summary(fake, make_repo, monkeypatch, capsys):
    monkeypatch.chdir(make_repo())
    fake.scenario(log=["fine\n"])
    assert cli.main(["check"]) == 0
    assert "failure summary" not in capsys.readouterr().err


def test_logs_summary_reads_only_the_tail(fake, capsys):
    fake.scenario(log=["early\n", "boom\n"], status_state="finished", outcome="failed",
                  exit_code=2, log_size=6 + summary.TAIL_BYTES)
    assert cli.main(["logs", JOB, "--summary"]) == 0
    out = capsys.readouterr().out
    assert f"failure summary of job {JOB}\n" in out and "exit code 2" in out
    read = [r for r in fake.requests() if r["type"] == "logs"]
    assert read and read[0]["body"]["offset"] == 6


def test_logs_summary_of_a_running_job_says_so(fake, capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # outside any project, so no warnings are looked up
    fake.scenario(status_state="running")
    assert cli.main(["logs", JOB, "--summary"]) == 0
    assert "running" in capsys.readouterr().out
    assert [r["type"] for r in fake.requests()] == ["status"]


def test_logs_summary_of_a_passed_job_has_no_failure(fake, capsys):
    fake.scenario(status_state="finished", outcome="passed", exit_code=0)
    assert cli.main(["logs", JOB, "--summary"]) == 0
    out = capsys.readouterr().out
    assert "passed" in out and "failure summary" not in out
