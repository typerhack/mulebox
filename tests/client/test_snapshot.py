import os
import socket
import stat
import tarfile

import pytest

from mulebox.client.snapshot import SnapshotError, current_fingerprint, make_snapshot

from .conftest import git

SECRETS = {
    ".env": "A=1",
    ".env.local": "B=2",
    ".secret/x": "pw",
    "a/secrets/b": "token",
    "id_ed25519": "key",
    "x.pem": "cert",
    ".npmrc": "//registry/:_authToken=abc",
    "reports/today.html": "report",
}


def members(snap):
    with tarfile.open(snap.path) as tar:
        return {m.name: m for m in tar.getmembers()}


def read(snap, name):
    with tarfile.open(snap.path) as tar:
        return tar.extractfile(name).read().decode()


@pytest.fixture
def snaps():
    made = []
    yield made
    for snap in made:
        snap.discard()


def snapshot(snaps, root, excludes=()):
    snap = make_snapshot(root, excludes)
    snaps.append(snap)
    return snap


def test_tracked_and_untracked_files_without_ignored(make_repo, snaps):
    repo = make_repo(
        tracked={"src/a.py": "print(1)", ".gitignore": "dist/\n"},
        untracked={"new.txt": "new", "dist/out.js": "built"},
    )
    names = set(members(snapshot(snaps, repo)))
    assert {".mulebox.yml", "src/a.py", ".gitignore", "new.txt"} <= names
    assert "dist/out.js" not in names
    assert not any(n.startswith(".git/") for n in names)


def test_secrets_never_enter_the_archive_even_when_tracked(make_repo, snaps):
    repo = make_repo(tracked=SECRETS, untracked={"b/.env.test": "C=3", "z.key": "k"})
    snap = snapshot(snaps, repo, ["reports/"])
    names = set(members(snap))
    assert names == {".mulebox.yml"}
    with open(snap.path, "rb") as fh:
        raw = fh.read()
    assert b"_authToken" not in raw


def test_only_a_tracked_env_template_enters_the_archive(make_repo, snaps):
    repo = make_repo(tracked={"api/.env.example": "A=", ".env.local": "B=2"},
                     untracked={".env.sample": "C="})
    names = set(members(snapshot(snaps, repo)))
    assert "api/.env.example" in names
    assert ".env.local" not in names and ".env.sample" not in names


def test_metadata_and_contents(make_repo, snaps):
    repo = make_repo(tracked={"run.sh": "#!/bin/sh\necho hi\n"})
    os.chmod(repo / "run.sh", 0o755)
    git(repo, "add", "run.sh")
    snap = snapshot(snaps, repo)
    info = members(snap)["run.sh"]
    assert info.mode & 0o777 == 0o755
    assert (info.uid, info.gid, info.uname, info.gname) == (0, 0, "", "")
    assert read(snap, "run.sh") == "#!/bin/sh\necho hi\n"
    assert snap.files == 2
    assert snap.base_commit == git(repo, "rev-parse", "HEAD").strip()
    assert snap.branch == "main"
    assert len(snap.sha256) == 64


def test_archive_is_private_and_discarded(make_repo):
    snap = make_snapshot(make_repo(), ())
    assert stat.S_IMODE(snap.path.stat().st_mode) == 0o600
    snap.discard()
    assert not snap.path.exists()
    snap.discard()  # twice is fine


def test_symlinks_are_stored_as_links_never_followed(make_repo, snaps, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE SECRET")
    repo = make_repo(tracked={"real.txt": "real"})
    os.symlink("real.txt", repo / "inside-link")
    os.symlink(str(outside), repo / "abs-link")
    os.symlink("../outside.txt", repo / "up-link")
    os.symlink(".env", repo / "to-env")
    snap = snapshot(snaps, repo)
    found = members(snap)
    assert found["inside-link"].issym() and found["inside-link"].linkname == "real.txt"
    assert found["to-env"].issym()
    assert "abs-link" not in found and "up-link" not in found
    assert set(snap.skipped_links) == {"abs-link", "up-link"}
    with open(snap.path, "rb") as fh:
        assert b"OUTSIDE SECRET" not in fh.read()


def test_tracked_file_under_a_directory_that_became_a_symlink(make_repo, snaps, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "f.txt").write_text("NOT OURS")
    repo = make_repo(tracked={"dir/f.txt": "ours"})
    (repo / "dir" / "f.txt").unlink()
    (repo / "dir").rmdir()
    os.symlink(str(elsewhere), repo / "dir")
    names = set(members(snapshot(snaps, repo)))
    assert "dir/f.txt" not in names


def test_vanished_files_sockets_and_fifos_are_skipped(make_repo, snaps):
    repo = make_repo(tracked={"gone.txt": "x", "keep.txt": "y"})
    (repo / "gone.txt").unlink()
    os.mkfifo(repo / "pipe")
    sock = socket.socket(socket.AF_UNIX)
    sock_path = repo / "s.sock"
    try:
        sock.bind(str(sock_path))
    except OSError:
        sock = None
    try:
        names = set(members(snapshot(snaps, repo)))
    finally:
        if sock is not None:
            sock.close()
    assert "keep.txt" in names
    assert not names & {"gone.txt", "pipe", "s.sock"}


def test_root_must_be_a_git_worktree(tmp_path):
    folder = tmp_path / "plain"
    folder.mkdir()
    with pytest.raises(SnapshotError, match="not inside a git worktree"):
        make_snapshot(folder, ())


def test_repo_without_commits_is_refused_before_packing(make_repo, snaps):
    """The coordinator requires a base commit; asking it would upload first and read badly."""
    with pytest.raises(SnapshotError, match="no commits yet"):
        snapshot(snaps, make_repo(commit=False))


def test_project_root_in_a_subfolder_sends_only_that_folder(make_repo, snaps):
    repo = make_repo(tracked={"app/.mulebox.yml": "x", "app/a.txt": "a", "other/b.txt": "b"})
    names = set(members(snapshot(snaps, repo / "app")))
    assert names == {".mulebox.yml", "a.txt"}


def test_fingerprint_matches_and_detects_changes(make_repo, snaps):
    repo = make_repo(tracked={"a.txt": "one"})
    snap = snapshot(snaps, repo)
    assert current_fingerprint(repo, ()) == snap.fingerprint
    (repo / ".env").write_text("secret change")  # excluded: not a change
    (repo / "a.txt").touch()  # mtime only: not a change
    assert current_fingerprint(repo, ()) == snap.fingerprint
    (repo / "a.txt").write_text("two")
    assert current_fingerprint(repo, ()) != snap.fingerprint


def test_fingerprint_sees_mode_and_new_files(make_repo, snaps):
    repo = make_repo(tracked={"a.txt": "one"})
    base = snapshot(snaps, repo).fingerprint
    os.chmod(repo / "a.txt", 0o755)
    assert current_fingerprint(repo, ()) != base
    os.chmod(repo / "a.txt", 0o644)
    (repo / "b.txt").write_text("new")
    assert current_fingerprint(repo, ()) != base


def test_too_large_snapshot_is_refused_and_removed(make_repo, monkeypatch, tmp_path):
    import tempfile

    from mulebox.client import snapshot as module

    temp = tmp_path / "tmp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    monkeypatch.setattr(module, "MAX_SNAPSHOT_BYTES", 10)
    with pytest.raises(SnapshotError, match="upload limit"):
        make_snapshot(make_repo(tracked={"a.txt": "x" * 1000}), ())
    assert list(temp.iterdir()) == []
