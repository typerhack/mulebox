"""The order of the line (coordinator/line.py, line_rules.py; M23.3, M24.4)."""

import pytest

from mulebox.common.protocol import JobState
from mulebox.coordinator import api, line, queue
from mulebox.coordinator import store as st

from .helpers import queued, request
from .test_reservations import T0, call, reserve

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


def test_the_defaults_keep_arrival_order_and_aging_alone_changes_nothing(store, staging):
    ids = [queued(store, staging, now=float(t), project=f"p{t % 3}") for t in range(8)]
    assert order(store) == arrival(store) == ids
    control(store, staging, ids[5], "first")
    control(store, staging, ids[2], "down")
    moved = order(store, 10.0)
    assert moved == [ids[5], ids[0], ids[1], ids[3], ids[2], ids[4], ids[6], ids[7]]
    for now in (10.0, 5 * HOUR, 40 * HOUR):  # aging alone, however long they waited
        assert order(store, now) == moved
    with store.read() as conn:
        for job_id in ids:
            job = st.require_job(conn, job_id)
            assert queue.position(conn, job, 40 * HOUR) == moved.index(job_id) + 1
            why = line.read(conn, 40 * HOUR).explain(job)
            assert bool(why) == (job_id in (ids[5], ids[2]))  # only a move has something to say


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


def lengths_of(monkeypatch, known):
    monkeypatch.setattr(line.usual, "lengths",
                        lambda conn, rows: {row["job_id"]: known.get(row["job"]) for row in rows})


def test_shortest_first_counts_a_job_with_no_history_as_the_lines_median(store, staging,
                                                                         monkeypatch):
    slow = queued(store, staging, now=1.0, job="slow")
    unknown = queued(store, staging, now=2.0, job="new")
    mid = queued(store, staging, now=3.0, job="mid")
    quick = queued(store, staging, now=4.0, job="quick")
    lengths_of(monkeypatch, {"slow": 600.0, "mid": 120.0, "quick": 30.0})
    rules(store, staging, shortest_first=True)
    assert order(store) == [quick, unknown, mid, slow]  # 120 s like mid, and it came first
    reply = api.handle(store, staging, request("status", job_id=unknown), 5.0)
    assert "no usual length yet, counted as the line's median 2m" in reply.body["place_reason"]
    assert reply.body["order"]["usual_s"] is None and reply.body["order"]["counted_as_s"] == 120.0


def test_shortest_first_with_no_length_known_keeps_arrival(store, staging, monkeypatch):
    ids = [queued(store, staging, now=float(t), job=f"j{t}") for t in range(3)]
    lengths_of(monkeypatch, {})
    rules(store, staging, shortest_first=True)
    assert order(store) == ids
    reply = api.handle(store, staging, request("status", job_id=ids[1]), 5.0)
    assert reply.body["place_reason"] == "no usual length in line yet; then by arrival"


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


def test_a_move_pins_only_the_moved_job_and_the_rules_still_order_the_rest(store, staging):
    a = queued(store, staging, now=1.0, project="example-app")
    b = queued(store, staging, now=2.0, project="example-api")
    c = queued(store, staging, now=3.0, project="example-web")
    control(store, staging, c, "up")
    assert order(store) == [a, c, b]
    with store.read() as conn:
        assert [(r["pin_side"], r["priority"]) for r in (st.require_job(conn, a),
                                                       st.require_job(conn, b))] == [(None, 0)] * 2
    rules(store, staging, projects={"example-api": 1})  # a later rule still moves the others
    assert order(store) == [c, b, a]  # c keeps its place just ahead of b
    reply = api.handle(store, staging, request("status", job_id=c), 4.0)
    assert reply.body["place_reason"] == f"moved by hand, just ahead of {b}"
    assert reply.body["order"]["moved"] == {"side": "before", "job_id": b, "in_line": True}
    reply = api.handle(store, staging, request("status", job_id=a), 4.0)
    assert reply.body["place_reason"] == "then by arrival"


def test_a_moved_job_takes_the_place_of_one_that_left_the_line(store, staging):
    low = queued(store, staging, now=1.0, project="example-low")
    other = queued(store, staging, now=2.0, project="example-app")
    rules(store, staging, projects={"example-low": -1})
    assert order(store) == [other, low]
    control(store, staging, low, "up")  # just ahead of other
    control(store, staging, low, "pause")
    assert claim(store, now=3.0) == other  # other leaves the line; low keeps its place
    later = queued(store, staging, now=4.0, project="example-app")
    assert order(store, 5.0) == [low, later]  # by its own level it would come last
    reply = api.handle(store, staging, request("status", job_id=low), 5.0)
    assert reply.body["place_reason"] == (f"moved by hand ahead of {other}, which has left the "
                                          "line, so in its place")
    assert reply.body["order"]["moved"]["in_line"] is False


def test_a_workflow_level_puts_its_runs_ahead(store, staging):
    agent = queued(store, staging, now=1.0)
    slots = {}
    for run, workflow in ((1, "Nightly"), (2, "CI")):
        reply = api.handle(store, staging, request(
            "reserve", worker="build-1", repository="example-org/example-app", job="test",
            run_id=str(run), run_attempt="1", runner="build-1-example-app", workflow=workflow),
            1.0 + run)
        slots[workflow] = reply.body["job_id"]
    assert order(store) == [agent, slots["Nightly"], slots["CI"]]
    body = rules(store, staging, workflows={"CI": "high", "Nightly": -1})
    assert body["rules"]["workflows"] == {"CI": 1, "Nightly": -1}
    assert order(store) == [slots["CI"], agent, slots["Nightly"]]
    reply = api.handle(store, staging, request("status", job_id=slots["CI"]), 5.0)
    assert reply.body["place_reason"] == "workflow CI +1; then by arrival"


def test_aging_is_said_in_whole_steps_so_a_reason_does_not_tick(store, staging):
    low = queued(store, staging, now=0.0, project="example-low")
    rules(store, staging, projects={"example-low": -1}, aging_min=30)
    reasons = set()
    for minute in (31, 45, 59):
        reply = api.handle(store, staging, request("status", job_id=low), minute * 60.0)
        reasons.add(reply.body["place_reason"])
    assert reasons == {"project example-low -1; waited 30m or more +1; then by arrival"}


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
    ({"workflows": {" CI": 1}}, "valid name"), ({"workflows": {"CI": 9}}, "level"),
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


def test_the_rules_say_each_projects_last_run_and_its_runs_of_the_last_seven_days(store, staging):
    day, now = 24 * HOUR, 100 * 24 * HOUR
    queued(store, staging, now=now - 40 * day, project="old-drill")
    queued(store, staging, now=now - 8 * day, project="example-app")
    for age in (6 * day, 2 * HOUR):
        queued(store, staging, now=now - age, project="example-app")
    waited = queued(store, staging, now=now - 9 * day, project="example-api")  # sent 9 days ago,
    with store.write() as conn:                                                # started 3 days ago
        conn.execute("UPDATE jobs SET started_at = ? WHERE job_id = ?", (now - 3 * day, waited))
    reserve(store, staging, now=now - HOUR)                                      # a GitHub run
    body = rules(store, staging, now=now, projects={"never-ran": 1})
    assert body["now"] == now
    assert body["project_activity"] == [
        {"name": "example-api", "last_run": now - 3 * day, "runs_7d": 1},
        {"name": "example-app", "last_run": now - 2 * HOUR, "runs_7d": 2},
        {"name": "example-org__example-app", "last_run": now - HOUR, "runs_7d": 1},
        {"name": "old-drill", "last_run": now - 40 * day, "runs_7d": 0},
    ]
    # The names alone, as before; a level for a project with no job has no entry in either.
    assert body["projects"] == [entry["name"] for entry in body["project_activity"]]
    assert body["rules"]["projects"] == {"never-ran": 1}


def test_an_unreadable_stored_value_falls_back_to_the_defaults(store, staging):
    with store.write() as conn:
        conn.execute("INSERT INTO meta (key, value) VALUES ('line_rules', 'not json')")
    reply = api.handle(store, staging, request("queue_rules"), 1.0)
    assert reply.body["rules"] == reply.body["defaults"]


def test_a_slot_moved_up_is_pinned_alone_and_says_so(store, staging):
    older = queued(store, staging, now=T0)
    res = reserve(store, staging, now=T0 + 1, workflow="CI")
    assert call(store, staging, "job_control", now=T0, job_id=res, action="up").body["position"] == 1
    status = call(store, staging, "status", now=T0 + 2, job_id=res).body
    assert status["place_reason"] == f"moved by hand, just ahead of {older}"
    assert status["moved"] == "before"
    with store.read() as conn:
        assert st.require_job(conn, older)["pin_side"] is None
        assert st.require_job(conn, res)["workflow"] == "CI"
