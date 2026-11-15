"""What a job's end line says of its tests (coordinator/test_proof.py, design.md Proof that tests
ran): how many ran, and, when that turned a pass into a failure, why and what to do."""

from __future__ import annotations

from typing import Any

EXIT_TESTS = 8  # a pass that did not prove its tests ran (coordinator/test_proof.py)
FAILING = ("zero", "fewer", "missing")


def _tests(result: dict[str, Any]) -> dict[str, Any]:
    tests = result.get("tests")
    return tests if isinstance(tests, dict) else {}


def failed_on_tests(result: dict[str, Any]) -> bool:
    return _tests(result).get("verdict") in FAILING


def _counts(runners: dict[str, Any]) -> str:
    parts = [f"{name} {item.get('ran', 0)}" for name, item in sorted(runners.items())
             if isinstance(item, dict)]
    return ", ".join(parts)


def _plural(n: Any) -> str:
    return f"{n} test" if n == 1 else f"{n} tests"


def _before(tests: dict[str, Any]) -> str:
    compared = tests.get("compared") or {}
    where = f" on {compared['branch']}" if compared.get("branch") else ""
    ran = compared.get("ran")
    return f"the last pass{where} ran {_plural(ran)} ({_counts(compared.get('runners') or {})})"


def sentence(result: dict[str, Any]) -> str:
    """The end of the outcome line: "" when the job's log showed no runner's summary."""
    tests = _tests(result)
    verdict = tests.get("verdict")
    if verdict == "missing":
        return ("; no test runner's summary in the log, and the project says `tests: required`. "
                "Run the tests so they print their summary, or set `tests: true`")
    runners = tests.get("runners")
    if not isinstance(runners, dict) or not runners:
        return ""
    ran = f"{_plural(tests.get('ran'))} ran ({_counts(runners)})"
    if verdict == "zero":
        return (f"; {ran}: a runner ran none, so the pass proves nothing. Check the test "
                "selection or paths; if no tests is right here, set `tests: false` for this job")
    if verdict == "fewer":
        return (f"; {ran}, {_before(tests)}. If tests were removed on purpose: "
                'mulebox check --fewer-tests "<why>"')
    if verdict == "allowed":
        return f"; {ran}, fewer than {_before(tests)}, allowed: {tests.get('fewer')}"
    return f"; {ran}"
