"""`mulebox fetch` and `--keep` on the dev machine (client/fetch.py)."""

import io
import tarfile

import pytest

from mulebox.client import fetch, summary
from mulebox.common.config import ProjectConfig

JOB = "job-01HZZZZZZZZZZZZZZZZZZZZZZZ"
KEPT = {"count": 2, "bytes": 8, "left_out": ["trace.zip: past keep_files_max (200.0 MB)"],
        "left_out_count": 1, "packed": True}
DONE = {"state": "finished", "outcome": "failed", "keep": ["shots/"], "files": KEPT}


def tar_of(files):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as tar:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return data.getvalue()


class Remote:
    def __init__(self, pack):
        self.pack = pack

    def download_files(self, job_id, dest):
        dest.write_bytes(self.pack)


def test_files_land_in_a_git_ignored_folder_of_the_project(tmp_path):
    err = io.StringIO()
    target = fetch.target_for(tmp_path, JOB, None)
    assert fetch.fetch(Remote(tar_of({"shots/a.png": b"png!", "shots/b.png": b"more"})), JOB,
                       DONE, target, err) == 0
    assert (tmp_path / ".mulebox" / "files" / JOB / "shots" / "a.png").read_bytes() == b"png!"
    assert (tmp_path / ".mulebox" / ".gitignore").read_text() == "*\n"
    out = err.getvalue()
    assert f"2 files kept (8 B), 1 left out, in {target.resolve()}" in out
    assert "not kept: trace.zip: past keep_files_max" in out


def test_a_second_fetch_replaces_the_first_and_nothing_beside_it(tmp_path):
    target = fetch.target_for(tmp_path, JOB, None)
    fetch.fetch(Remote(tar_of({"old.txt": b"1"})), JOB, DONE, target, io.StringIO())
    (target.parent / "other-job").mkdir()
    fetch.fetch(Remote(tar_of({"new.txt": b"2"})), JOB, DONE, target, io.StringIO())
    assert sorted(p.name for p in target.iterdir()) == ["new.txt"]
    assert (target.parent / "other-job").is_dir()


def test_dash_o_puts_them_in_a_folder_of_the_job_inside_it(tmp_path):
    chosen = tmp_path / "downloads"
    chosen.mkdir()
    (chosen / "mine.txt").write_text("stays")
    target = fetch.target_for(tmp_path, JOB, chosen)
    fetch.fetch(Remote(tar_of({"a.txt": b"1"})), JOB, DONE, target, io.StringIO())
    assert target == chosen / JOB and (chosen / "mine.txt").read_text() == "stays"


def test_a_pack_reaching_out_of_its_folder_is_refused_and_leaves_nothing(tmp_path):
    target = fetch.target_for(tmp_path, JOB, None)
    with pytest.raises(Exception, match="refusing|outside|\\.\\."):
        fetch.fetch(Remote(tar_of({"../escape.txt": b"no"})), JOB, DONE, target, io.StringIO())
    assert not (tmp_path / ".mulebox" / "escape.txt").exists() and not target.exists()


def test_a_folder_that_cannot_be_made_is_named(tmp_path):
    (tmp_path / "file").write_text("not a folder")
    with pytest.raises(fetch.FetchError, match="cannot make"):
        fetch.fetch(Remote(b""), JOB, DONE, tmp_path / "file" / "x" / JOB, io.StringIO())


@pytest.mark.parametrize("status, said", [
    ({"state": "finished"}, "named no files"),
    ({**DONE, "state": "running"}, "once it ended"),
    ({**DONE, "files": {**KEPT, "packed": False}}, "kept no files"),
])
def test_what_has_nothing_to_fetch_says_so(tmp_path, status, said):
    with pytest.raises(fetch.FetchError, match=said):
        fetch.fetch(Remote(b""), JOB, status, tmp_path / "t" / JOB, io.StringIO())


def test_keep_on_the_command_line_adds_to_the_jobs_own():
    project = ProjectConfig(project="example-app", jobs={"check": "true"}, keep=("coverage/",))
    assert fetch.with_keep(project, ("shots/", "coverage/")).keep == ("coverage/", "shots/")
    with pytest.raises(fetch.FetchError, match="inside the project"):
        fetch.with_keep(project, ("../x",))


def test_the_end_of_a_job_and_its_summary_name_the_fetch():
    assert fetch.kept_lines(JOB, DONE) == [f"2 files kept (8 B), 1 left out: mulebox fetch {JOB}"]
    assert fetch.kept_lines(JOB, {"files": {**KEPT, "packed": False}})[0].endswith(
        f"none to fetch (`mulebox logs {JOB}` says why)")
    assert fetch.kept_lines(JOB, {}) == []
    lines = summary.render(JOB, {"outcome": "failed", "exit_code": 1, "files": KEPT}, ["boom"])
    assert f"mulebox fetch {JOB}" in "\n".join(lines) and lines[-1] == "| boom"
