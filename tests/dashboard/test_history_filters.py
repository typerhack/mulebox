"""The History page's filters: `/api/history` checks them and keeps them while paging."""

import pytest

from mulebox.coordinator import store as st
from mulebox.coordinator.errors import BadRequest
from mulebox.dashboard.history_query import MAX_TEXT, filters

from .conftest import NOW


@pytest.fixture
def jobs(data, run_job, finish_job):
    """Five finished jobs of three projects; returns a helper giving the names a filter keeps."""
    made = {}
    for n, (name, project, job, branch, outcome) in enumerate([
        ("a", "example-app", "check", "main", "passed"),
        ("b", "example-app", "e2e", "feature/50%_off", "failed"),
        ("c", "other-app", "check", "main-2", "timed_out"),
        ("d", "other-app", "lint", "fix-ui", "cancelled"),
        ("e", "Example-App", "check", "main-3", "interrupted"),
    ]):
        job_id, state = run_job(now=NOW + n, project=project, job=job, branch=branch)
        finish_job(state, outcome, 0 if outcome == "passed" else 1, now=NOW + 100 + n)
        made[job_id] = name

    def kept(**chosen):
        return [made[row["job_id"]] for row in data.history(chosen=chosen)["jobs"]]
    return kept, {name: job_id for job_id, name in made.items()}


def test_each_filter_is_an_exact_value(jobs):
    kept, _ = jobs
    assert kept(project="other-app") == ["d", "c"]
    assert kept(job="check") == ["e", "c", "a"]
    assert kept(worker="wrk-a", client="alice@dev machine") == ["e", "d", "c", "b", "a"]
    assert kept(kind="runner") == []
    assert kept(project="other-app", job="lint") == ["d"]


def test_result_means_what_the_lists_show(jobs, data, store):
    kept, ids = jobs
    assert kept(result="passed") == ["a"]
    assert kept(result="failed") == ["e", "c", "b"]  # timed out and interrupted are failures
    assert kept(result="cancelled") == ["d"]
    with store.write() as conn:  # stopped as stuck: shown so, a cancelled outcome on the wire
        st.update_job(conn, ids["d"], stop_reason="stuck")
    assert kept(result="cancelled") == ["d"]
    with store.write() as conn:  # a GitHub run with no result of its own shows `released`
        st.update_job(conn, ids["a"], kind="runner")
    assert data.history()["jobs"][-1]["shown_state"] == "released"
    assert kept(result="passed") == []


def test_search_finds_part_of_project_job_or_branch_in_any_case(jobs):
    kept, _ = jobs
    assert kept(q="EXAMPLE") == ["e", "b", "a"]
    assert kept(q="2e") == ["b"]
    assert kept(q="fix") == ["d"]
    assert kept(q="50%_") == ["b"]
    assert kept(q="%") == ["b"]  # a wildcard is taken as typed
    assert kept(q="_") == ["b"]
    assert kept(q="mai", project="other-app") == ["c"]


def test_paging_keeps_the_filters(jobs, data):
    first = data.history(limit=1, chosen={"job": "check"})
    assert first["choices"]["project"] == ["Example-App", "example-app", "other-app"]
    second = data.history(limit=1, before=first["next_before"], chosen={"job": "check"})
    third = data.history(limit=1, before=second["next_before"], chosen={"job": "check"})
    assert [r["job"] for r in first["jobs"] + second["jobs"] + third["jobs"]] == ["check"] * 3
    assert "choices" not in second  # only the first page lists them
    assert data.history(limit=1, before=third["next_before"], chosen={"job": "check"})["jobs"] == []


@pytest.mark.parametrize("query, problem", [
    ({"kind": "upgrade"}, "kind"), ({"result": "released"}, "result"),
    ({"q": "x" * (MAX_TEXT + 1)}, "q"), ({"project": "x" * (MAX_TEXT + 1)}, "project")])
def test_bad_filters_are_refused(query, problem):
    with pytest.raises(BadRequest, match=problem):
        filters(query)


def test_empty_and_unknown_parameters_are_left_out():
    assert filters({"project": "", "q": "  ", "limit": "5", "other": "x"}) == {}
    assert filters({"q": " a b ", "kind": "job"}) == {"kind": "job", "q": "a b"}


def test_the_route_filters_and_answers_400(call, jobs):
    async def go(client):
        found = await (await client.get("/api/history?project=other-app&result=failed")).json()
        bad = [(await client.get(f"/api/history?{q}")).status
               for q in ("kind=upgrade", "result=nope", f"q={'x' * (MAX_TEXT + 1)}")]
        return found, bad
    found, bad = call(go)
    assert [row["outcome"] for row in found["jobs"]] == ["timed_out"]
    assert "job" in found["choices"]
    assert bad == [400, 400, 400]
