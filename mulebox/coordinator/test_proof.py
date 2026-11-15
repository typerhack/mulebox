"""Proof that tests ran (docs/design.md): a pass is held to the tests its log shows.

At submit, `settings` keeps what the dev machine said in `jobs.tests`: the mode (`auto`, `off`,
`required`), the default branch to compare a branch's first pass with, and the reason when an
agent lets this run pass with fewer tests. When the job ends, `judge` counts the tests in its
stored log (common/test_counts.py) and, for a pass, gives the verdict:

- `ok`: every runner the last pass had ran at least as many tests;
- `zero`: a runner ran no test;
- `fewer`: a runner ran fewer tests than the last pass of the same job, on the same branch, else
  on the default branch;
- `allowed`: fewer, with the agent's reason;
- `missing`: `tests: required` and no runner's summary at all;
- null: nothing to check (no summary, `tests: false`, a failed job).

`zero`, `fewer` and `missing` turn the pass into a failure with EXIT_TESTS. Counts are kept for
every outcome, so the history shows how a suite grew. `mulebox run` is held to zero only, its
command changing from run to run, and `warm` and GitHub runs are not counted.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from mulebox.common import test_counts
from mulebox.common.protocol import Outcome
from mulebox.coordinator import validate as v

EXIT_TESTS = 8
FAILING = ("zero", "fewer", "missing")
MODES = ("auto", "off", "required")
_FROM_RUN = "run"  # mulebox run's job name (client/job_body.py RUN_JOB_NAME)
MAX_REASON = 300


def settings(body: dict[str, Any]) -> dict[str, Any]:
    """What a submit said; an older client says nothing, which is `auto`."""
    given = body.get("tests") if isinstance(body.get("tests"), dict) else {}
    mode = given.get("mode") if given.get("mode") in MODES else "auto"
    base = v.text(given, "base", None)
    fewer = v.text(given, "fewer", None)
    return {"mode": mode, "base": base or None,
            "fewer": fewer[:MAX_REASON] if fewer else None}


def counted(job: dict[str, Any], log: Path) -> test_counts.Counts | None:
    """The job's counts from its log, None when it is not counted at all."""
    said = job.get("tests") or {}
    if job.get("kind") != "job" or job.get("job") == "warm" or said.get("mode") == "off":
        return None
    try:
        with log.open(encoding="utf-8", errors="replace") as lines:
            return test_counts.count(lines)
    except OSError:
        return {}


def _last_pass(conn: sqlite3.Connection, job: dict[str, Any], branch: str | None
               ) -> dict[str, Any] | None:
    if not branch:
        return None
    row = conn.execute(
        "SELECT job_id, branch, tests FROM jobs WHERE project = ? AND job = ? AND branch = ? "
        "AND outcome = 'passed' AND job_id != ? AND tests LIKE '%\"runners\"%' "
        "ORDER BY finished_at DESC LIMIT 1",
        (job["project"], job["job"], branch, job["job_id"])).fetchone()
    if row is None:
        return None
    tests = json.loads(row[2] or "{}")
    return {"job_id": row[0], "branch": row[1], "ran": tests.get("ran"),
            "runners": tests.get("runners") or {}}


def _verdict(job: dict[str, Any], runners: test_counts.Counts,
             compared: dict[str, Any] | None) -> str | None:
    said = job.get("tests") or {}
    if not runners:
        return "missing" if said.get("mode") == "required" else None
    if any(item["ran"] == 0 for item in runners.values()):
        return "zero"
    if compared and job.get("job") != _FROM_RUN:
        before = compared["runners"]
        if any(runners.get(name, {}).get("ran", 0) < item.get("ran", 0)
               for name, item in before.items()):
            return "allowed" if said.get("fewer") else "fewer"
    return "ok"


def judge(conn: sqlite3.Connection, job: dict[str, Any], runners: test_counts.Counts | None,
          outcome: Outcome, exit_code: int | None) -> tuple[dict[str, Any] | None, Outcome,
                                                            int | None]:
    """(what `jobs.tests` becomes, the outcome, the exit code)."""
    if runners is None:
        return job.get("tests"), outcome, exit_code
    said = job.get("tests") or {}
    found = {**said, "runners": runners, "ran": test_counts.total(runners),
             "skipped": sum(item["skipped"] for item in runners.values()),
             "verdict": None, "compared": None}
    if outcome is not Outcome.PASSED:
        return found, outcome, exit_code
    compared = _last_pass(conn, job, job.get("branch")) or _last_pass(conn, job, said.get("base"))
    found["compared"] = compared
    found["verdict"] = _verdict(job, runners, compared)
    if found["verdict"] in FAILING:
        found["command_exit"] = exit_code
        return found, Outcome.FAILED, EXIT_TESTS
    return found, outcome, exit_code
