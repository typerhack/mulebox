"""Feedback drafts: what they hold, and that nothing private can be posted."""

import subprocess

import pytest

from mulebox.cli import main
from mulebox.client import feedback, feedback_commands
from mulebox.common.anonymize import Anonymizer
from mulebox.common.config import ClientConfig

SCRUB = Anonymizer(["example-app", "build-1"])
JOB = {"job_id": "job-1", "state": "finished", "outcome": "failed", "exit_code": 2,
       "duration_s": 3.5, "project": "example-app", "branch": "secret-feature"}
CLEAN = "# worker lost a job\n\n## What happened\n\nThe job vanished.\n"


def client(repo="example-org/mulebox"):
    return ClientConfig(coordinator="build-1", feedback_repo=repo)


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """No project, no coordinator; `gh` recorded, never run."""
    monkeypatch.chdir(tmp_path)
    sent = []

    def fake_gh(argv):
        sent.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "https://example.invalid/issues/1\n", "")
    monkeypatch.setattr(feedback_commands, "run_gh", fake_gh)
    monkeypatch.setattr(feedback_commands, "_queue_or_nothing", lambda config: [])
    monkeypatch.setattr(feedback_commands, "load_client_config", client)
    return tmp_path, sent


def test_draft_holds_the_result_but_no_identifying_job_fields():
    text = feedback.draft("It broke on example-app", "1.2.3", SCRUB, JOB)
    assert "# It broke on [private]" in text and "exit_code: 2" in text
    assert "outcome: failed" in text and "mulebox 1.2.3" in text
    for private in ("example-app", "secret-feature", "job-1"):
        assert private not in text


def test_log_is_scrubbed_and_capped():
    log = "\n".join(f"line {n} /home/alice/app" for n in range(200))
    text = feedback.draft("x", "1", SCRUB, JOB, log)
    assert "alice" not in text and "line 199" in text and "line 100" not in text


def test_no_log_section_unless_given():
    assert "```" not in feedback.draft("x", "1", SCRUB, JOB)


def test_names_in_covers_every_project_in_the_queue_not_just_this_one():
    jobs = [{"project": "one", "branch": "b1", "worker": "w1", "client": "c1"},
            {"project": "two", "branch": None}]
    assert feedback.names_in(jobs) == {"one", "b1", "w1", "c1", "two"}


def test_local_names_include_the_git_identity_and_repository(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    git("init")
    git("config", "user.name", "Alice Example")
    git("config", "user.email", "alice@example.com")
    git("remote", "add", "origin", "git@github.com:example-org/example-app.git")
    names = feedback.local_names(None, tmp_path, client())
    assert {"Alice Example", "alice@example.com", "example-org", "example-app",
            "example-org/example-app", "build-1", tmp_path.name} <= names


def test_a_hand_added_private_detail_blocks_the_post():
    feedback.check_clean(CLEAN, SCRUB)
    with pytest.raises(feedback.FeedbackError, match="line 6"):
        feedback.check_clean(CLEAN + "Details at 10.0.0.1\n", SCRUB)


def test_a_real_draft_passes_its_own_check():
    feedback.check_clean(feedback.draft("It broke on example-app", "1", SCRUB, JOB,
                                        "see /home/alice/x"), SCRUB)


@pytest.mark.parametrize("text", ["", "no title", "# ", "## wrong level\n"])
def test_draft_needs_a_title(text):
    with pytest.raises(feedback.FeedbackError):
        feedback.title_of(text)


def test_cli_draft_sends_nothing_and_works_with_no_coordinator(cli, capsys):
    _, sent = cli
    code = main(["feedback", "draft", "--summary", "cannot reach build-1 at 10.0.0.1"])
    out = capsys.readouterr().out
    assert code == 0 and sent == [] and "10.0.0.1" not in out and "build-1" not in out


def test_cli_post_sends_exactly_the_reviewed_file(cli, capsys):
    folder, sent = cli
    path = folder / "draft.md"
    path.write_text(CLEAN)
    assert main(["feedback", "post", str(path)]) == 0
    assert sent == [["gh", "issue", "create", "--repo", "example-org/mulebox", "--title",
                     "worker lost a job", "--body-file", str(path)]]


def test_cli_post_refuses_a_private_detail_with_a_clean_error(cli, capsys):
    folder, sent = cli
    path = folder / "draft.md"
    path.write_text(CLEAN + "Host 192.168.1.50 failed\n")
    assert main(["feedback", "post", str(path)]) == 2
    assert sent == [] and "nothing was sent" in capsys.readouterr().err


def test_cli_post_is_off_until_a_repository_is_configured(cli, monkeypatch, capsys):
    folder, sent = cli
    monkeypatch.setattr(feedback_commands, "load_client_config", lambda: client(None))
    path = folder / "draft.md"
    path.write_text(CLEAN)
    assert main(["feedback", "post", str(path)]) == 2
    assert sent == [] and "feedback_repo" in capsys.readouterr().err


def test_cli_log_needs_a_job(cli, capsys):
    assert main(["feedback", "draft", "--log", "--summary", "x"]) == 2


def test_gh_failure_is_reported_not_raised(cli, monkeypatch, capsys):
    folder, _ = cli
    monkeypatch.setattr(feedback_commands, "run_gh", lambda argv: subprocess.CompletedProcess(
        argv, 1, "", "HTTP 404"))
    path = folder / "draft.md"
    path.write_text(CLEAN)
    assert main(["feedback", "post", str(path)]) == 2
    assert "HTTP 404" in capsys.readouterr().err


def test_gh_missing_is_reported_not_raised(cli, monkeypatch, capsys):
    from mulebox.runners.github import GitHubError
    folder, _ = cli

    def missing(argv):
        raise GitHubError("cannot run the GitHub CLI `gh`")
    monkeypatch.setattr(feedback_commands, "run_gh", missing)
    path = folder / "draft.md"
    path.write_text(CLEAN)
    assert main(["feedback", "post", str(path)]) == 2


def test_a_title_keeps_its_semicolons():
    text = feedback.draft("env order is wrong; keys come sorted; see the job", "1", SCRUB)
    assert text.splitlines()[0] == "# env order is wrong; keys come sorted; see the job"


def test_a_long_title_is_cut_at_a_word_and_the_summary_stays_whole():
    summary = "word; " * 60
    text = feedback.draft(summary, "1", SCRUB)
    title = feedback.title_of(text)
    assert len(title) <= feedback.TITLE_CHARS and title.endswith("word")
    assert summary.strip() in text
