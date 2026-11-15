"""A pass is held to the tests its log shows (test_proof.py, design.md Proof that tests ran)."""

from mulebox.coordinator import store as st
from mulebox.coordinator.test_proof import EXIT_TESTS, settings

from .test_attendance import T0, call, running


def ends(store, staging, log, outcome="passed", code=0, branch="feature", job="check", **sent):
    run = running(store, staging, branch=branch, job=job, tests=sent or {"mode": "auto"})
    staging.log_path(run["job_id"]).parent.mkdir(parents=True, exist_ok=True)
    staging.log_path(run["job_id"]).write_text(log)
    call(store, staging, "result", T0 + 50, outcome=outcome, exit_code=code, duration_s=1.0, **run)
    with store.read() as conn:
        return st.require_job(conn, run["job_id"])


PASS_40 = "==== 40 passed, 2 skipped in 3.10s ====\n"
PASS_38 = "==== 38 passed in 3.00s ====\n"


def test_a_pass_keeps_its_counts(store, staging):
    job = ends(store, staging, "building\n" + PASS_40)
    assert job["outcome"] == "passed" and job["exit_code"] == 0
    assert job["tests"]["ran"] == 40 and job["tests"]["skipped"] == 2
    assert job["tests"]["verdict"] == "ok"


def test_zero_tests_fail_with_their_own_code(store, staging):
    job = ends(store, staging, "==== no tests ran in 0.01s ====\n")
    assert (job["outcome"], job["exit_code"]) == ("failed", EXIT_TESTS)
    assert job["tests"]["verdict"] == "zero" and job["tests"]["command_exit"] == 0


def test_fewer_than_the_branch_last_pass_fail(store, staging):
    ends(store, staging, PASS_40)
    job = ends(store, staging, PASS_38)
    assert (job["outcome"], job["exit_code"]) == ("failed", EXIT_TESTS)
    assert job["tests"]["verdict"] == "fewer" and job["tests"]["compared"]["ran"] == 40


def test_the_pass_it_was_compared_with_says_when_it_finished(store, staging):
    before = ends(store, staging, PASS_40)
    compared = ends(store, staging, PASS_38)["tests"]["compared"]
    assert compared["job_id"] == before["job_id"]
    assert compared["finished_at"] == before["finished_at"] == T0 + 50


def test_a_reason_lets_fewer_pass(store, staging):
    ends(store, staging, PASS_40)
    job = ends(store, staging, PASS_38, mode="auto", fewer="removed the old importer")
    assert job["outcome"] == "passed" and job["tests"]["verdict"] == "allowed"
    assert job["tests"]["fewer"] == "removed the old importer"


def test_a_new_branch_compares_with_the_default_branch(store, staging):
    ends(store, staging, PASS_40, branch="main")
    job = ends(store, staging, PASS_38, branch="new-work", mode="auto", base="main")
    assert job["tests"]["verdict"] == "fewer" and job["tests"]["compared"]["branch"] == "main"


def test_more_tests_are_fine(store, staging):
    ends(store, staging, PASS_38)
    assert ends(store, staging, PASS_40)["tests"]["verdict"] == "ok"


def test_no_summary_is_no_verdict_unless_required(store, staging):
    assert ends(store, staging, "done\n")["outcome"] == "passed"
    job = ends(store, staging, "done\n", mode="required")
    assert (job["outcome"], job["exit_code"], job["tests"]["verdict"]) == (
        "failed", EXIT_TESTS, "missing")


def test_off_counts_nothing(store, staging):
    job = ends(store, staging, "==== no tests ran in 0.01s ====\n", mode="off")
    assert job["outcome"] == "passed" and "runners" not in job["tests"]


def test_a_failure_keeps_counts_and_its_own_code(store, staging):
    job = ends(store, staging, "==== 3 failed, 37 passed in 3.00s ====\n", "failed", 1)
    assert (job["exit_code"], job["tests"]["ran"], job["tests"]["verdict"]) == (1, 40, None)


def test_a_failure_is_not_what_a_pass_is_compared_with(store, staging):
    ends(store, staging, "==== 3 failed, 47 passed in 3.00s ====\n", "failed", 1)
    assert ends(store, staging, PASS_40)["tests"]["compared"] is None


def test_mulebox_run_is_held_to_zero_only(store, staging):
    ends(store, staging, PASS_40, job="run")
    assert ends(store, staging, PASS_38, job="run")["outcome"] == "passed"
    assert ends(store, staging, "==== no tests ran in 0.01s ====\n", job="run")["outcome"] == "failed"


def test_warm_is_not_counted(store, staging):
    job = ends(store, staging, "==== no tests ran in 0.01s ====\n", job="warm")
    assert job["outcome"] == "passed"


def test_an_older_client_is_auto():
    assert settings({}) == {"mode": "auto", "base": None, "fewer": None}
    assert settings({"tests": {"mode": "bogus", "fewer": "x" * 999}})["fewer"] == "x" * 300


def test_the_summary_lines_are_kept_for_the_dashboard(store, staging):
    job = ends(store, staging, "\x1b[32m==== 40 passed, 2 skipped in 3.10s ====\x1b[0m\nok\n")
    assert job["tests"]["lines"] == {"pytest": ["==== 40 passed, 2 skipped in 3.10s ===="]}
