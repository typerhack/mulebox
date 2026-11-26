"""`keep:` entries (common/keep_files.py) and how a job gets them (config_jobs.for_job)."""

import pytest

from mulebox.common import keep_files
from mulebox.common.config import ConfigError, load_project_config
from mulebox.common.config_jobs import for_job

HEAD = "project: example-app\n"


def load(tmp_path, text):
    path = tmp_path / ".mulebox.yml"
    path.write_text(HEAD + text)
    return load_project_config(path)


@pytest.mark.parametrize("entry", ["coverage/lcov.info", "test-results/", "playwright-report",
                                   "test-results/**/*.png", "*.log", "a/**"])
def test_files_folders_and_patterns_are_taken(entry):
    assert keep_files.problem(entry) is None


@pytest.mark.parametrize("entry, why", [
    ("", "empty"), ("/etc/passwd", "relative"), ("../up", "inside the project"),
    ("a/../../b", "relative"), ("a\\b", "plain path"), ("shots/[ab].png", "only * and **"),
    (".mulebox/files", "mulebox's own"), (".", "inside the project"),
])
def test_what_cannot_be_kept_says_why(entry, why):
    assert why in keep_files.problem(entry)


def test_at_most_twenty_and_each_once():
    assert keep_files.checked(["a", "b", "a"]) == ("a", "b")
    with pytest.raises(ValueError, match="at most 20"):
        keep_files.checked([f"f{n}" for n in range(21)])


def test_top_level_keep_reaches_every_job_and_a_job_can_replace_it(tmp_path):
    project = load(tmp_path, "keep: [coverage/]\njobs:\n  check: pytest\n"
                   "  e2e:\n    run: npx playwright test\n    keep: [playwright-report/, test-results/]\n"
                   "  lint:\n    run: ruff check\n    keep: []\n")
    assert for_job(project, "check")[0].keep == ("coverage/",)
    assert for_job(project, "e2e")[0].keep == ("playwright-report/", "test-results/")
    assert for_job(project, "lint")[0].keep == ()
    assert for_job(project, None)[0].keep == ("coverage/",)  # `mulebox run`


def test_a_bad_entry_names_the_field(tmp_path):
    with pytest.raises(ConfigError, match="keep.*inside the project"):
        load(tmp_path, "keep: [../x]\njobs:\n  check: pytest\n")


def test_the_summary_line():
    assert keep_files.summary(None) is None
    assert keep_files.summary({"count": 0, "left_out_count": 0}) is None
    assert keep_files.summary({"count": 1, "bytes": 2_500_000}) == "1 file kept (2.5 MB)"
    assert keep_files.summary({"count": 12, "bytes": 3400, "left_out_count": 2}) == \
        "12 files kept (3.4 KB), 2 left out"
