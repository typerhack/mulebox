"""The end line says how many tests ran, and why a pass became exit 8."""

from mulebox.client import report, summary

RUNNERS = {"pytest": {"ran": 38, "skipped": 0}}


def result(verdict, **tests):
    return {"outcome": "failed" if verdict in ("zero", "fewer", "missing") else "passed",
            "exit_code": 8 if verdict in ("zero", "fewer", "missing") else 0, "duration_s": 3.0,
            "tests": {"runners": RUNNERS, "ran": 38, "verdict": verdict, **tests}}


COMPARED = {"branch": "main", "ran": 40, "runners": {"pytest": {"ran": 40, "skipped": 0}}}


def test_a_pass_says_how_many_ran():
    line = report.outcome_line("j1", result("ok"))
    assert line.endswith("passed in 3s; 38 tests ran (pytest 38)")


def test_fewer_names_the_last_pass_and_the_flag():
    body = result("fewer", compared=COMPARED)
    line = report.outcome_line("j1", body)
    assert "failed (exit 8: tests)" in line and "the last pass on main ran 40 tests" in line
    assert "--fewer-tests" in line and report.exit_code_for(body) == 8
    assert not summary.wanted(body)


def test_allowed_shows_the_reason():
    line = report.outcome_line("j1", result("allowed", compared=COMPARED, fewer="dropped old API"))
    assert line.endswith("allowed with fewer than the last pass on main (40 tests): dropped old API")


def test_zero_and_missing_say_what_to_do():
    zero = result("zero", runners={"pytest": {"ran": 0, "skipped": 0}}, ran=0)
    assert "tests: false" in report.outcome_line("j1", zero)
    assert "tests: required" in report.outcome_line("j1", result("missing", runners={}))


def test_no_counts_change_nothing():
    assert report.outcome_line("j1", {"outcome": "passed", "duration_s": 3.0}).endswith("in 3s")
    assert summary.wanted({"outcome": "failed", "exit_code": 1})
