"""What the commands print of a job that looks stuck (client/stuck_lines.py, attention.py)."""

from mulebox.client import attention, events, stuck_lines

JOB = "job-01ABC"
STUCK = {"verdict": "stuck", "text": "Looks stuck: no output and no CPU for 3m 10s.",
         "number": 1, "limit_s": 120.0}


def test_a_stuck_job_says_not_to_send_it_again_and_how_to_look_or_stop():
    line = stuck_lines.stuck_line(JOB, STUCK)
    assert line.startswith(f"job {JOB}: Looks stuck")
    assert "Do not send it again" in line and f"mulebox logs {JOB}" in line
    assert f"mulebox cancel {JOB}" in line


def test_a_slow_job_goes_on_by_itself():
    line = stuck_lines.stuck_line(JOB, {**STUCK, "verdict": "slow", "text": "Downloading slowly."})
    assert "It goes on by itself" in line and "Do not send" not in line


def test_check_and_wait_print_it_once_per_spell():
    key, line = attention.notice(JOB, {"state": "running", "stuck": STUCK})
    assert key == ("stuck", 1) and line.startswith(attention.WARNING)
    key, line = attention.notice(JOB, {"state": "running", "moving": {"number": 1}})
    assert key == ("moving", 1) and line == f"job {JOB} is working again"


def test_events_has_the_stuck_event():
    event = events.event_of(events.Message(events.MessageType.STATUS_OK,
                                           "r", {"job_id": JOB, "state": "running",
                                                 "stuck": STUCK}))
    assert event["event"] == "stuck" and event["verdict"] == "stuck"
    assert events.as_text(event).startswith(f"{attention.WARNING}job {JOB}: Looks stuck")


def test_status_shows_it_only_when_it_is_not_working():
    assert stuck_lines.status_line(JOB, {"verdict": "working"}) is None
    assert stuck_lines.status_line(JOB, STUCK).startswith("  stuck (after 2m 00s with nothing")
    lines = attention.status_lines({"job_id": JOB, "looks": STUCK})
    assert any("Looks stuck" in line for line in lines)
