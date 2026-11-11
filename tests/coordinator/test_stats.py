"""Job minutes (`stats`): what counts, cut at a range's edges, filters and breakdowns."""

import pytest

from mulebox.coordinator import api, stats
from mulebox.coordinator import store as st
from mulebox.coordinator.errors import BadRequest
from mulebox.coordinator.stats_api import ask

from .helpers import queued, request

DAY = 86400.0


def ran(store, staging, started, seconds, state="finished", **fields):
    """A job that started at `started` and ran `seconds` (None: not known)."""
    job_id = queued(store, staging, now=started - 5)
    with store.write() as conn:  # straight to the end state: only the columns matter here
        conn.execute("UPDATE jobs SET state = ? WHERE job_id = ?", (state, job_id))
        st.update_job(conn, job_id, started_at=started, duration_s=seconds,
                      worker=fields.pop("worker", "build-1"), **fields)
    return job_id


def total(store, start, end, now=10 * DAY, **filters):
    with store.read() as conn:
        return stats.summary(conn, start, end, now, filters)


def test_finished_running_and_unknown_runs(store, staging):
    ran(store, staging, DAY + 100, 600)
    ran(store, staging, DAY + 200, 60, kind="runner", client="github")
    ran(store, staging, DAY + 300, None, outcome="interrupted")
    ran(store, staging, DAY + 400, None, state="running")
    ran(store, staging, DAY + 500, 30, kind="upgrade")  # not a job
    found = total(store, DAY, 2 * DAY, now=DAY + 1000)
    assert found["total"] == {"seconds": 1260.0, "runs": 3, "running": 1,
                              "running_seconds": 600.0, "unknown": 1}
    assert found["first_started_at"] == DAY + 100


def test_a_run_across_midnight_counts_on_both_days(store, staging):
    ran(store, staging, 2 * DAY - 120, 300)
    with store.read() as conn:
        found = stats.summary(conn, DAY, 3 * DAY, 10 * DAY, day_starts=[DAY, 2 * DAY])
    assert [day["seconds"] for day in found["days"]] == [120.0, 180.0]
    assert found["days"][0]["kinds"] == {"job": 120.0, "runner": 0.0}
    assert found["total"]["seconds"] == 300.0
    assert total(store, 3 * DAY, 4 * DAY)["total"]["runs"] == 0


def test_an_old_run_of_unknown_length_stays_on_its_own_day(store, staging):
    ran(store, staging, DAY, None, outcome="interrupted")
    assert total(store, 5 * DAY, 6 * DAY)["total"]["unknown"] == 0
    assert total(store, 0, 6 * DAY)["total"]["unknown"] == 1


def test_filters_and_breakdowns(store, staging):
    ran(store, staging, DAY, 100, project="example-app")
    ran(store, staging, DAY, 50, project="example-app", kind="runner", client="github",
        worker="build-2")
    ran(store, staging, DAY, 10, project="other-app")
    found = total(store, 0, 2 * DAY)
    assert [(row["key"], row["seconds"]) for row in found["by"]["project"]] == [
        ("example-app", 150.0), ("other-app", 10.0)]
    assert {row["key"] for row in found["by"]["worker"]} == {"build-1", "build-2"}
    assert total(store, 0, 2 * DAY, client="github")["total"]["seconds"] == 50.0
    assert total(store, 0, 2 * DAY, worker="build-1", project="example-app")["total"]["seconds"] == 100.0
    with store.read() as conn:
        assert stats.choices(conn)["client"] == ["alice@dev machine", "github"]


def test_the_request_checks_its_body_and_replies(store, staging):
    ran(store, staging, DAY, 100)
    with pytest.raises(BadRequest, match="kind"):
        ask({"kind": "upgrade"}, 10.0)
    with pytest.raises(BadRequest, match="by"):
        ask({"by": ["branch"]}, 10.0)
    with pytest.raises(BadRequest, match="day_starts"):
        ask({"day_starts": [2.0, 1.0]}, 10.0)
    reply = api.handle(store, staging, request("stats", by=["project"]), 2 * DAY)
    assert reply.type == "stats_ok", reply.body
    assert reply.body["total"]["seconds"] == 100.0 and list(reply.body["by"]) == ["project"]
    assert reply.body["choices"]["kind"] == ["job"]
