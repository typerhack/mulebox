"""Test counts from runners' own summaries (common/test_counts.py), on lines as they print them."""

import pytest

from mulebox.common.test_counts import count, total


def lines(text):
    return text.strip("\n").splitlines()


@pytest.mark.parametrize("text, expected", [
    ("3462 passed, 5 skipped in 62.57s (0:01:02)", {"pytest": {"ran": 3462, "skipped": 5}}),
    ("===== 2 failed, 40 passed, 1 xfailed, 3 warnings in 4.20s =====",
     {"pytest": {"ran": 43, "skipped": 0}}),
    ("============ no tests ran in 0.01s ============", {"pytest": {"ran": 0, "skipped": 0}}),
    ("===== 7 deselected in 0.05s =====", {"pytest": {"ran": 0, "skipped": 7}}),
    ("      Tests  2 failed | 211 passed | 3 skipped (216)", {"vitest": {"ran": 213, "skipped": 3}}),
    ("      Tests  213 passed (213)", {"vitest": {"ran": 213, "skipped": 0}}),
    ("Tests:       1 failed, 2 skipped, 40 passed, 43 total", {"jest": {"ran": 41, "skipped": 2}}),
    ("  Tests:    2 failed, 23 passed (50 assertions)", {"pest": {"ran": 25, "skipped": 0}}),
    ("OK (25 tests, 50 assertions)", {"phpunit": {"ran": 25, "skipped": 0}}),
    ("Tests: 25, Assertions: 50, Failures: 1, Skipped: 2.", {"phpunit": {"ran": 23, "skipped": 2}}),
    ("test result: ok. 12 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.1s\n"
     "test result: ok. 3 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out",
     {"cargo": {"ran": 16, "skipped": 1}}),
    ("  12 passing (30ms)\n  2 pending\n  1 failing", {"mocha": {"ran": 13, "skipped": 2}}),
    ("Running 14 tests using 4 workers\n  1 failed\n  11 passed (30.1s)\n  2 skipped",
     {"playwright": {"ran": 12, "skipped": 2}}),
    ("--- PASS: TestA (0.00s)\n    --- PASS: TestA/sub (0.00s)\n--- SKIP: TestB (0.00s)\n"
     "--- FAIL: TestC (0.01s)", {"go": {"ran": 2, "skipped": 1}}),
    ("Test run with 12 tests in 3 suites passed after 0.1 seconds.",
     {"swift-testing": {"ran": 12, "skipped": 0}}),
])
def test_each_runner(text, expected):
    assert count(lines(text)) == expected


def test_xctest_counts_the_run_once_not_each_bundle_again():
    log = """
Test Suite 'AppTests.xctest' passed at 2026-11-15 10:00:01.000.
\t Executed 12 tests, with 2 tests skipped and 0 failures (0 unexpected) in 0.5 (0.6) seconds
Test Suite 'All tests' passed at 2026-11-15 10:00:01.000.
\t Executed 12 tests, with 2 tests skipped and 0 failures (0 unexpected) in 0.5 (0.6) seconds
"""
    assert count(lines(log)) == {"xctest": {"ran": 10, "skipped": 2}}


def test_one_bundle_alone_counts():
    log = "Test Suite 'AppTests.xctest' failed at x.\n Executed 4 tests, with 1 failure (0 unexpected) in 0.1 (0.1) seconds"
    assert count(lines(log)) == {"xctest": {"ran": 4, "skipped": 0}}


def test_colours_are_taken_out_and_a_gate_sums_and_keeps_runners_apart():
    log = ["\x1b[32m3462 passed\x1b[0m, 5 skipped in 62.57s", "      Tests  213 passed (213)",
           "2 passed in 0.10s"]
    found = count(log)
    assert found == {"pytest": {"ran": 3464, "skipped": 5}, "vitest": {"ran": 213, "skipped": 0}}
    assert total(found) == 3677


@pytest.mark.parametrize("line", ["3 passed the review", "Tests: see below", "OK (done)",
                                  "  12 passed (30.1s)", "Executed 3 tests, with 0 failures"])
def test_ordinary_lines_are_no_count(line):
    assert count([line]) == {}
