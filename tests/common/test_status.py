from mulebox.common import status


def job(state, **extra):
    return {"job_id": "j", "state": state, **extra}


def test_sections_cover_every_state():
    assert status.section_of(job("starting")) == "running"
    assert status.section_of(job("cleaning")) == "running"
    assert status.section_of(job("uploading")) == "queued"
    assert status.section_of(job("finished")) == "recent"
    assert status.section_of(job("nonsense")) is None


def test_shown_state_is_the_outcome_when_finished():
    assert status.shown_state(job("finished", outcome="timed_out")) == "timed_out"
    assert status.shown_state(job("running", outcome=None)) == "running"


def test_finished_runner_slot_shows_released_but_keeps_abnormal_outcomes():
    assert status.shown_state(job("finished", outcome="passed", kind="runner")) == "released"
    assert status.shown_state(job("finished", outcome="failed", kind="runner")) == "released"
    assert status.shown_state(job("finished", outcome="interrupted", kind="runner")) == "interrupted"


def test_elapsed_by_state():
    assert status.elapsed_s(job("queued", created_at=90.0), 100.0) == 10.0
    assert status.elapsed_s(job("running", created_at=50.0, started_at=90.0), 100.0) == 10.0
    assert status.elapsed_s(job("finished", duration_s=7.0), 100.0) == 7.0
    assert status.elapsed_s(job("finished", started_at=1.0, finished_at=4.0), 100.0) == 3.0
    assert status.elapsed_s(job("finished"), 100.0) is None


def test_malformed_fields_never_raise():
    bad = job("running", created_at="soon", started_at=True, position="x")
    assert status.elapsed_s(bad, 100.0) is None
    assert status.row(bad, 100.0)["section"] == "running"


def test_sections_are_ordered():
    jobs = [job("queued", job_id="q2", position=2), job("queued", job_id="q1", position=1),
            job("finished", job_id="old", finished_at=1.0),
            job("finished", job_id="new", finished_at=2.0)]
    parts = dict(status.sections(jobs))
    assert [j["job_id"] for j in parts["queued"]] == ["q1", "q2"]
    assert [j["job_id"] for j in parts["recent"]] == ["new", "old"]


def test_fingerprint_ignores_the_passing_of_time():
    first = job("running", started_at=1.0)
    assert status.fingerprint([first]) == status.fingerprint([dict(first)])
    assert status.fingerprint([first]) != status.fingerprint([job("cleaning", started_at=1.0)])


def test_fingerprint_sees_where_a_waiting_job_may_go_change():
    waiting = job("queued", position=1, can_run_on=["build-1"])
    assert status.fingerprint([waiting]) != status.fingerprint([{**waiting, "can_run_on": []}])
    assert status.fingerprint([waiting]) != status.fingerprint(
        [{**waiting, "waiting_for": "no build machine for this job is online"}])
    assert status.fingerprint([waiting]) == status.fingerprint([{**waiting, "elapsed_s": 5.0}])
