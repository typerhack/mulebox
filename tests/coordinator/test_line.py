"""The order of the line (coordinator/line.py, line_rules.py; M23.3, M24.4)."""

import pytest

from mulebox.common.protocol import JobState
from mulebox.coordinator import api, line, queue
from mulebox.coordinator import store as st

from .helpers import queued, request

HOUR = 3600.0


def rules(store, staging, now=1000.0, **change):
    reply = api.handle(store, staging, request("queue_rules", action="set", rules=change), now)
    assert reply.type == "queue_rules_ok", reply.body
    return reply.body


def order(store, now=1000.0):
    with store.read() as conn:
        return [row["job_id"] for row in line.read(conn, now).rows]


def arrival(store):
    """The line as the coordinator ordered it before the rules (queue.QUEUE_ORDER in SQL)."""
    with store.read() as conn:
        return [r["job_id"] for r in st.select_jobs(conn, "state = ?", (JobState.QUEUED.value,),
                                                    "priority DESC, queued_at, seq")]


def claim(store, now=1000.0, worker="wrk-a"):
    job = queue.claim(store, worker, ["node", "docker"], 4, 10, now=now)
    return job["job_id"] if job else None


def control(store, staging, job_id, action, now=1000.0):
    reply = api.handle(store, staging, request("job_control", job_id=job_id, action=action), now)
    assert reply.type == "status_ok", reply.body
    return reply.body


def test_the_defaults_keep_arrival_order_with_moves_and_aging(store, staging):
    ids = [queued(store, staging, now=float(t), project=f"p{t % 3}") for t in range(8)]
    control(store, staging, ids[5], "first")
    control(store, staging, ids[2], "down")
    before = arrival(store)
    for now in (10.0, 5 * HOUR, 40 * HOUR):  # aging alone, however long they waited
        assert order(store, now) == before
    with store.read() as conn:
        for job_id in ids:
            job = st.require_job(conn, job_id)
            assert queue.position(conn, job, 40 * HOUR) == before.index(job_id) + 1
            assert line.read(conn, 40 * HOUR).explain(job) == {}  # nothing to say by default


def test_a_high_project_goes_ahead_and_says_why(store, staging):
    older = queued(store, staging, now=1.0, project="example-app")
    newer = queued(store, staging, now=2.0, project="example-api")
    rules(store, staging, projects={"example-api": "high"})
    assert order(store) == [newer, older]
    reply = api.handle(store, staging, request("status", job_id=newer), 3.0)
    assert reply.body["position"] == 1
    assert reply.body["place_reason"] == "project example-api +1; then by arrival"
    assert reply.body["order"]["levels"] == [{"rule": "project", "name": "example-api", "level": 1}]
    assert claim(store) == newer


def test_branch_rules_take_the_exact_name_else_the_longest_pattern(store, staging):
    feature = queued(store, staging, now=1.0, branch="feature-x")
    release = queued(store, staging, now=2.0, branch="release/1.2")
    main = queued(store, staging, now=3.0, branch="main")
    rules(store, staging, branches={"main": 2, "release/*": 1, "*": -1, "release/1.*": 3})
    assert order(store) == [release, main, feature]
    with store.read() as conn:
        why = line.read(conn, 4.0).explain(st.require_job(conn, release))
    assert why["order"]["levels"][0] == {"rule": "branch", "name": "release/1.*", "level": 3}


def test_aging_lets_a_low_project_catch_up(store, staging):
    low = queued(store, staging, now=0.0, project="example-low")
    rules(store, staging, projects={"example-low": -1}, aging_min=30)
    fresh = queued(store, staging, now=29 * 60.0, project="example-app")
    assert order(store, now=29 * 60.0) == [fresh, low]
    assert order(store, now=31 * 60.0) == [low, fresh]  # +1 for 30 min waited: level 0, older


def test_fair_turns_let_a_single_job_pass_a_burst(store, staging):
    burst = [queued(store, staging, now=float(t), project="example-app") for t in range(3)]
    single = queued(store, staging, now=10.0, project="example-api")
    rules(store, staging, fair_turns=True)
    assert order(store) == [burst[0], single, burst[1], burst[2]]
    assert claim(store) == burst[0]  # now example-app runs one, so example-api has the next turn
    assert order(store) == [single, burst[1], burst[2]]
    reply = api.handle(store, staging, request("queue", limit=0), 11.0)
    reasons = {row["job_id"]: row.get("place_reason") for row in reply.body["jobs"]}
    assert reasons[single] == "turn 1 of example-api; then by arrival"
    assert reasons[burst[2]] == "turn 3 of example-app; then by arrival"


def test_shortest_first_puts_known_short_jobs_first(store, staging, monkeypatch):
    slow = queued(store, staging, now=1.0, job="slow")
    unknown = queued(store, staging, now=2.0, job="new")
    quick = queued(store, staging, now=3.0, job="quick")
    lengths = {"slow": 600.0, "quick": 30.0}
    monkeypatch.setattr(line.usual, "job_seconds", lambda conn, job: lengths.get(job["job"]))
    rules(store, staging, shortest_first=True)
    assert order(store) == [quick, slow, unknown]
    reply = api.handle(store, staging, request("status", job_id=unknown), 4.0)
    assert "no usual length yet" in reply.body["place_reason"]


def test_a_github_level_puts_ci_runs_ahead_of_agent_jobs(store, staging):
    agent = queued(store, staging, now=1.0)
    reply = api.handle(store, staging, request(
        "reserve", worker="build-1", repository="example-org/example-app", job="test",
        run_id="1", run_attempt="1", runner="build-1-example-app"), 2.0)
    slot = reply.body["job_id"]
    rules(store, staging, github=1)
    assert order(store) == [slot, agent]
    granted = api.handle(store, staging, request("acquire", job_id=slot), 3.0, cluster_slots=1)
    assert granted.body["state"] == "running"


def test_moves_come_first_and_keep_the_order_they_set(store, staging):
    a = queued(store, staging, now=1.0, project="example-app")
    b = queued(store, staging, now=2.0, project="example-api")
    rules(store, staging, projects={"example-api": 1})
    assert order(store) == [b, a]
    control(store, staging, b, "down")
    later = queued(store, staging, now=3.0, project="example-api")
    assert order(store) == [a, b, later]  # the moved line stays; a later job goes behind it
    reply = api.handle(store, staging, request("status", job_id=b), 4.0)
    assert reply.body["place_reason"] == "in the order last set by hand"


def test_a_paused_project_still_holds_its_place_under_the_rules(store, staging):
    high = queued(store, staging, now=1.0, project="example-api")
    other = queued(store, staging, now=2.0, project="example-app")
    rules(store, staging, projects={"example-api": 1})
    api.handle(store, staging, request("project_pause", action="pause",
                                       projects=["example-api"]), 3.0)
    assert order(store) == [high, other] and claim(store, now=3.0) == other


@pytest.mark.parametrize("change, problem", [
    ({"projects": {"example-app": 4}}, "level"), ({"projects": {"../x": 1}}, "valid name"),
    ({"branches": {"has space": 1}}, "valid name"), ({"github": "loud"}, "github"),
    ({"aging_min": -1}, "aging_min"), ({"fair_turns": "yes"}, "fair_turns"),
    ({"colour": 1}, "rules"), ("all", "rules"),
])
def test_bad_rules_are_refused(store, staging, change, problem):
    reply = api.handle(store, staging, request("queue_rules", action="set", rules=change), 1.0)
    assert reply.body["code"] == "bad_request" and problem in reply.body["message"]


def test_rules_merge_entry_by_entry_normal_removes_and_reset_clears(store, staging):
    queued(store, staging, project="example-app")
    rules(store, staging, projects={"example-app": "high", "example-api": -2})
    body = rules(store, staging, projects={"example-api": "normal"}, branches={"main": 1})
    assert body["rules"]["projects"] == {"example-app": 1}
    assert body["rules"]["branches"] == {"main": 1}
    assert body["projects"] == ["example-app"] and body["levels"]["max"] == 3
    reply = api.handle(store, staging, request("queue_rules", action="reset"), 1.0)
    assert reply.body["rules"] == reply.body["defaults"]
    with store.read() as conn:
        assert conn.execute("SELECT 1 FROM meta WHERE key = 'line_rules'").fetchone() is None


def test_an_unreadable_stored_value_falls_back_to_the_defaults(store, staging):
    with store.write() as conn:
        conn.execute("INSERT INTO meta (key, value) VALUES ('line_rules', 'not json')")
    reply = api.handle(store, staging, request("queue_rules"), 1.0)
    assert reply.body["rules"] == reply.body["defaults"]
