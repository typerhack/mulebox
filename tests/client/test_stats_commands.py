"""`mulebox stats`: local days, the request body and the printed table."""

import argparse
import time

from mulebox.client import stats_commands as sc


def test_days_start_at_local_midnight_today_last():
    now = time.mktime((2026, 3, 30, 15, 0, 0, 0, 0, -1))
    days = sc.day_starts(3, now)
    assert [time.localtime(day)[:6] for day in days] == [
        (2026, 3, 28, 0, 0, 0), (2026, 3, 29, 0, 0, 0), (2026, 3, 30, 0, 0, 0)]


def test_body_maps_names_to_the_coordinators():
    args = argparse.Namespace(project=None, source="github", machine="build-1", kind="ci",
                              by="machine", days=2)
    found = sc.body(args, time.time())
    assert {k: found[k] for k in ("client", "worker", "kind", "by")} == {
        "client": "github", "worker": "build-1", "kind": "runner", "by": ["worker"]}
    assert len(found["day_starts"]) == 2


def test_render():
    row = {"seconds": 3720, "runs": 3, "running": 1, "unknown": 0}
    found = {"first_started_at": 0, "total": row, "days": [{"from": 0, **row}],
             "by": {"client": [{"key": "github", **row}, {"key": "alice@laptop", **row}]}}
    lines = sc.render(found, "source")
    assert "1h 02m  3 runs  1 running" in lines[1]
    assert any(line.strip().startswith("GitHub") for line in lines)
    assert sc.render({"first_started_at": None, "filters": {"project": "x"}}, "project") == [
        "No job has run yet that fits these filters."]
