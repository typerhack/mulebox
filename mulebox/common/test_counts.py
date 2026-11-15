"""How many tests a job ran, from the summaries test runners print (docs/design.md, Proof that
tests ran). Pure: text in, counts out.

`count(lines)` gives `{runner: {"ran": n, "skipped": n}}` for every runner whose summary it saw,
summed when a runner printed several (a gate running pytest twice, cargo's one line per crate).
`ran` is tests that ran, passed or failed; skipped, ignored and pending ones are `skipped`. A
runner it does not know is not there: no summary is no count, never zero.

`read(lines)` gives the counts and, per runner, the summary lines it counted (up to
`MAX_LINES`, as printed less colour codes), so the dashboard can find them in the log without a
second set of patterns. Go has no summary line, only one per test, so it gives none.

Lines are matched after colour codes are taken out, as runners colour their summaries. Each
pattern is anchored on words that runner alone prints, so an ordinary line ("3 passed the
review") is not read as a count.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

Counts = dict[str, dict[str, int]]
Lines = dict[str, list[str]]
MAX_LINES = 5

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_N = r"(\d+)"

# pytest: "==== 3462 passed, 5 skipped in 62.57s ====", or the same without the rules (-q).
_PYTEST = re.compile(r"^=*\s*((?:\d+ (?:passed|failed|skipped|errors?|xfailed|xpassed|deselected|"
                     r"warnings?|rerun)(?:, )?)+)\s+in [\d.]+s(?: \([\d:]+\))?\s*=*\s*$")
_PYTEST_EMPTY = re.compile(r"^=*\s*no tests ran in [\d.]+s\s*=*\s*$")
# vitest: "      Tests  2 failed | 211 passed | 3 skipped (216)"
_VITEST = re.compile(r"^\s*Tests\s{2,}((?:\d+ (?:passed|failed|skipped|todo)(?: \| )?)+)\s+\(\d+\)")
# jest: "Tests:       1 failed, 2 skipped, 40 passed, 43 total"
_JEST = re.compile(r"^Tests:\s+((?:\d+ (?:passed|failed|skipped|todo|pending)(?:, )?)+),?\s*"
                   r"\d+ total")
# Pest: "  Tests:    2 failed, 23 passed (50 assertions)"
_PEST = re.compile(r"^\s*Tests:\s+((?:\d+ (?:passed|failed|skipped|risky|incomplete|todo|"
                   r"warnings?)(?:, )?)+)\s*\(\d+ assertions?")
# PHPUnit: "OK (25 tests, 50 assertions)" or "Tests: 25, Assertions: 50, Failures: 1, Skipped: 2."
_PHPUNIT_OK = re.compile(r"^OK \(" + _N + r" tests?, \d+ assertions?\)")
_PHPUNIT = re.compile(r"^Tests: " + _N + r", Assertions: \d+(.*)$")
# cargo: "test result: ok. 12 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out"
_CARGO = re.compile(r"^test result: \w+\. " + _N + r" passed; " + _N + r" failed; " + _N
                    + r" ignored")
# mocha: "  12 passing (30ms)", "  2 pending", "  1 failing"
_MOCHA = re.compile(r"^\s+" + _N + r" (passing|pending|failing)(?: \(\d+m?s\))?\s*$")
# Playwright: "Running 14 tests using 4 workers", then "  12 passed (30.1s)", "  2 skipped".
_PW_START = re.compile(r"^Running \d+ tests? using \d+ workers?")
_PW = re.compile(r"^\s+" + _N + r" (passed|failed|skipped|flaky|did not run|interrupted)"
                 r"(?: \([\d.]+m?s\))?\s*$")
# XCTest (swift test, xcodebuild test): "Executed 12 tests, with 1 failure (0 unexpected) in ..."
# after "Test Suite 'All tests' passed|failed"; Swift Testing: "Test run with 12 tests passed".
# A bundle's line comes first, then the run's own ('All tests' or 'Selected tests'), which wins.
_XC_SUITE = re.compile(r"^Test Suite '(All tests|Selected tests|.*\.xctest)' (passed|failed)")
_XC = re.compile(r"^\s*Executed " + _N + r" tests?, with ")
_XC_SKIP = re.compile(r"(\d+) tests? skipped")
_SWIFT_TESTING = re.compile(r"Test run with " + _N + r" tests?(?: in \d+ suites?)? (passed|failed)")
# Go with -v: "--- PASS: TestName (0.00s)", "--- FAIL: ...", "--- SKIP: ..."
_GO = re.compile(r"^--- (PASS|FAIL|SKIP): \S+")  # top-level tests; subtests are indented

_RAN = {"passed", "failed", "errors", "error", "xfailed", "xpassed", "passing", "failing",
        "risky", "incomplete", "warning", "warnings", "flaky", "interrupted"}
_SKIPPED = {"skipped", "todo", "pending", "deselected", "did not run"}


def _parts(text: str) -> tuple[int, int]:
    """("3 passed, 2 skipped" or "2 failed | 3 passed") -> (ran, skipped)."""
    ran = skipped = 0
    for number, word in re.findall(r"(\d+) ([a-z ]+?)(?=,|\||$|\s*\()", text.strip()):
        word = word.strip()
        if word in _SKIPPED:
            skipped += int(number)
        elif word in _RAN and word not in ("warning", "warnings"):
            ran += int(number)
    return ran, skipped


class _Tally:
    def __init__(self) -> None:
        self.counts: Counts = {}
        self.lines: Lines = {}
        self.current = ""  # the line being read
        self.playwright = False
        self.xc_suite: str | None = None  # the suite whose "Executed" line comes next
        self.xc_run: list[int] | None = None  # ran, skipped of the whole run
        self.xc_bundles: list[int] | None = None

    def add(self, runner: str, ran: int, skipped: int = 0, line: str | None = None) -> None:
        found = self.counts.setdefault(runner, {"ran": 0, "skipped": 0})
        found["ran"] += ran
        found["skipped"] += skipped
        self.keep(runner, self.current if line is None else line)

    def keep(self, runner: str, line: str) -> None:
        kept = self.lines.setdefault(runner, [])
        if line and len(kept) < MAX_LINES and line not in kept:
            kept.append(line)

    def line(self, line: str) -> None:  # noqa: C901 - one branch per runner, in one place
        self.current = line
        if match := _PYTEST.match(line):
            self.add("pytest", *_parts(match.group(1)))
        elif _PYTEST_EMPTY.match(line):
            self.add("pytest", 0)
        elif match := _VITEST.match(line):
            self.add("vitest", *_parts(match.group(1).replace(" | ", ", ")))
        elif match := _JEST.match(line):
            self.add("jest", *_parts(match.group(1)))
        elif match := _PEST.match(line):
            self.add("pest", *_parts(match.group(1)))
        elif match := _PHPUNIT_OK.match(line):
            self.add("phpunit", int(match.group(1)))
        elif match := _PHPUNIT.match(line):
            rest = match.group(2)
            skipped = sum(int(n) for n in re.findall(r"(?:Skipped|Incomplete): (\d+)", rest))
            self.add("phpunit", int(match.group(1)) - skipped, skipped)
        elif match := _CARGO.match(line):
            self.add("cargo", int(match.group(1)) + int(match.group(2)), int(match.group(3)))
        elif _PW_START.match(line):
            self.playwright = True
        elif self.playwright and (match := _PW.match(line)):
            word = match.group(2)
            self.add("playwright", 0 if word in _SKIPPED else int(match.group(1)),
                     int(match.group(1)) if word in _SKIPPED else 0)
        elif match := _MOCHA.match(line):
            number, word = int(match.group(1)), match.group(2)
            self.add("mocha", 0 if word == "pending" else number, number if word == "pending" else 0)
        elif match := _XC_SUITE.match(line):
            self.xc_suite = match.group(1)
        elif self.xc_suite and (match := _XC.match(line)):
            skip = _XC_SKIP.search(line)
            skipped = int(skip.group(1)) if skip else 0
            pair = [int(match.group(1)) - skipped, skipped]
            self.keep("xctest", line)
            if self.xc_suite.endswith(".xctest"):
                self.xc_bundles = [a + b for a, b in zip(self.xc_bundles or [0, 0], pair)]
            else:
                self.xc_run = [a + b for a, b in zip(self.xc_run or [0, 0], pair)]
            self.xc_suite = None
        elif match := _SWIFT_TESTING.search(line):
            self.add("swift-testing", int(match.group(1)))
        elif match := _GO.match(line):
            self.add("go", 0 if match.group(1) == "SKIP" else 1, 1 if match.group(1) == "SKIP" else 0,
                     line="")


    def finish(self) -> Counts:
        xc = self.xc_run if self.xc_run is not None else self.xc_bundles
        if xc is not None:
            self.add("xctest", *xc, line="")
        return self.counts


def read(lines: Iterable[str]) -> tuple[Counts, Lines]:
    """(the counts, each runner's summary lines) of a log."""
    tally = _Tally()
    for raw in lines:
        tally.line(_ANSI.sub("", raw).rstrip("\r\n"))
    counts = tally.finish()
    return counts, {name: kept for name, kept in tally.lines.items() if kept and name in counts}


def count(lines: Iterable[str]) -> Counts:
    return read(lines)[0]


def total(counts: Counts) -> int:
    return sum(item["ran"] for item in counts.values())
