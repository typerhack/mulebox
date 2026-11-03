import io

from mulebox.client import tui
from mulebox.client.queue_view import COLUMNS, job_row, render_screen, render_table

NOW = 10_000.0


def job(n, state, **extra):
    base = {
        "job_id": f"job-01JC3X00000000000000000{n:03d}",
        "project": "example-app",
        "job": "check",
        "branch": "main",
        "client": "laptop",
        "state": state,
        "outcome": None,
        "exit_code": None,
        "worker": None,
        "position": None,
        "created_at": NOW - 100 + n,
        "started_at": None,
        "finished_at": None,
    }
    base.update(extra)
    return base


JOBS = [
    job(1, "finished", outcome="passed", started_at=NOW - 500, finished_at=NOW - 380),
    job(2, "running", started_at=NOW - 65, worker="build-1"),
    job(3, "queued", position=2),
    job(4, "queued", position=1, branch="feature/very-long-branch-name-that-goes-on"),
    job(5, "finished", outcome="failed", exit_code=2, started_at=NOW - 50, finished_at=NOW - 8),
]


def test_row_columns():
    row = job_row(JOBS[1], NOW)
    assert dict(zip(COLUMNS, row)) == {
        "ID": "000000002"[-8:], "PROJECT": "example-app", "JOB": "check", "BRANCH": "main",
        "STATE": "running", "ELAPSED": "1m 05s", "POS": "-",
    }


def test_finished_shows_outcome_and_run_time():
    row = dict(zip(COLUMNS, job_row(JOBS[0], NOW)))
    assert row["STATE"] == "passed" and row["ELAPSED"] == "2m 00s"


def test_queued_shows_position_and_wait():
    row = dict(zip(COLUMNS, job_row(JOBS[2], NOW)))
    assert row["POS"] == "2" and row["ELAPSED"] == "1m 37s"


def test_sections_and_order():
    lines = render_table(JOBS, NOW, width=200)
    assert lines[0].split() == list(COLUMNS)
    text = "\n".join(lines)
    assert text.index("Running (1)") < text.index("Queued (2)") < text.index("Recent (2)")
    queued = [ln for ln in lines if " queued " in ln]
    assert "feature/" in queued[0]  # position 1 first
    recent = text[text.index("Recent"):]
    assert recent.index("failed") < recent.index("passed")  # newest first


def test_width_and_truncation():
    lines = render_table(JOBS, NOW, width=40)
    assert all(len(ln) <= 40 for ln in lines)
    wide = render_table(JOBS, NOW, width=500)
    assert any("~" in ln for ln in wide)  # long branch cut with a marker


def test_empty_queue():
    lines = render_table([], NOW)
    assert lines.count("  none") == 3


def test_control_characters_from_data_are_neutralised():
    lines = render_table([job(1, "queued", branch="evil\x1b[2Jbranch")], NOW, width=200)
    assert "\x1b" not in "\n".join(lines)


def test_full_ids_for_the_plain_table():
    lines = render_table(JOBS[:1], NOW, width=200, full_ids=True)
    assert JOBS[0]["job_id"] in "\n".join(lines)


def test_screen_has_exact_height():
    for height in (3, 5, 30):
        lines = render_screen(JOBS, NOW, 80, height, "header", "footer")
        assert len(lines) == height and lines[-1] == "footer"
    assert render_screen(JOBS, NOW, 80, 6, "h", "f")[-2] == "..."


def test_live_loop_redraws_until_q_and_shows_errors():
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("build-1 unreachable")
        return JOBS

    keys = iter(["", "", "q"])
    out = io.StringIO()
    tui.live(fetch, "build-1", out, lambda t: next(keys), lambda: (100, 20), clock=lambda: NOW)
    frames = out.getvalue().split(tui.HOME_CLEAR)[1:]
    assert len(frames) == 3
    assert "error: build-1 unreachable" in frames[1]
    assert "running" in frames[1]  # the last good data stays on screen
    assert "q quits" in frames[2]


def test_watch_without_a_terminal_prints_once(monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr("sys.stdin", io.StringIO())
    assert tui.watch(lambda: JOBS, "build-1", out) == 0
    assert "\x1b" not in out.getvalue() and "Running (1)" in out.getvalue()


def test_terminal_is_restored_on_error(monkeypatch):
    import termios
    import tty

    saved = []
    monkeypatch.setattr(termios, "tcgetattr", lambda fd: ["state"])
    monkeypatch.setattr(termios, "tcsetattr", lambda fd, when, attrs: saved.append(attrs))
    monkeypatch.setattr(tty, "setcbreak", lambda fd: None)
    out = io.StringIO()
    try:
        with tui._terminal(0, out):
            raise ValueError("boom")
    except ValueError:
        pass
    assert saved == [["state"]]
    assert out.getvalue().startswith(tui.ENTER) and out.getvalue().endswith(tui.LEAVE)
