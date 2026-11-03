"""Safe tar extraction: escapes are refused before anything is written."""

import io
import tarfile

import pytest

from mulebox.common.safepath import PathOutsideRoots
from mulebox.worker.archive import ArchiveError, extract_tar

from .fakes import make_tar


def _tar_with(path, *members):
    with tarfile.open(path, "w:gz") as tar:
        for info, data in members:
            tar.addfile(info, io.BytesIO(data) if data is not None else None)
    return path


def _file(name, data=b"x"):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    return info, data


def _link(name, target, kind=tarfile.SYMTYPE):
    info = tarfile.TarInfo(name)
    info.type = kind
    info.linkname = target
    return info, None


def test_extracts_regular_files(tmp_path, paths):
    archive = make_tar(tmp_path / "a.tar.gz", {"a.txt": "A", "dir/b.txt": "B"})
    dest = extract_tar(archive, paths.jobs / "p" / "src", paths.roots)
    assert (dest / "a.txt").read_text() == "A"
    assert (dest / "dir" / "b.txt").read_text() == "B"


@pytest.mark.parametrize("member", [
    _file("../escape.txt"),
    _file("/abs.txt"),
    _file("dir/../../escape.txt"),
    _link("link", "/etc/passwd"),
    _link("link", "../../outside"),
    _link("hard", "../outside", tarfile.LNKTYPE),
])
def test_refuses_escaping_members(tmp_path, paths, member):
    archive = _tar_with(tmp_path / "bad.tar.gz", _file("ok.txt"), member)
    with pytest.raises(ArchiveError):
        extract_tar(archive, paths.jobs / "p" / "src", paths.roots)
    assert not (paths.jobs / "p" / "src" / "ok.txt").exists()
    assert not (tmp_path / "escape.txt").exists()


def test_refuses_device_entries(tmp_path, paths):
    info = tarfile.TarInfo("dev")
    info.type = tarfile.CHRTYPE
    archive = _tar_with(tmp_path / "dev.tar.gz", (info, None))
    with pytest.raises(ArchiveError, match="special"):
        extract_tar(archive, paths.jobs / "p" / "src", paths.roots)


def test_file_through_an_inside_symlink_stays_inside(tmp_path, paths):
    outside = tmp_path / "outside"
    outside.mkdir()
    archive = _tar_with(tmp_path / "via.tar.gz", _link("sub", "."), _file("sub/ok.txt"))
    dest = extract_tar(archive, paths.jobs / "p" / "src", paths.roots)
    assert (dest / "ok.txt").exists()
    assert list(outside.iterdir()) == []


def test_relative_symlink_inside_is_kept(tmp_path, paths):
    archive = _tar_with(tmp_path / "l.tar.gz", _file("bin/tool"), _link("tool", "bin/tool"))
    dest = extract_tar(archive, paths.jobs / "p" / "src", paths.roots)
    assert (dest / "tool").is_symlink()


def test_strip_prefix(tmp_path, paths):
    archive = make_tar(tmp_path / "n.tar.xz", {"node-v1/bin/node": "#!", "node-v1/LICENSE": "L"},
                       mode="w:xz")
    dest = extract_tar(archive, paths.cache / "t", paths.roots, strip_prefix="node-v1")
    assert (dest / "bin" / "node").exists()
    with pytest.raises(ArchiveError, match="not under"):
        extract_tar(archive, paths.cache / "u", paths.roots, strip_prefix="other")


def test_destination_must_be_inside_roots(tmp_path, paths):
    archive = make_tar(tmp_path / "a.tar.gz", {"a.txt": "A"})
    with pytest.raises(PathOutsideRoots):
        extract_tar(archive, tmp_path / "elsewhere", paths.roots)


def test_corrupt_archive(tmp_path, paths):
    bad = tmp_path / "bad.tar.gz"
    bad.write_bytes(b"not a tar")
    with pytest.raises(ArchiveError, match="cannot extract"):
        extract_tar(bad, paths.jobs / "p" / "src", paths.roots)
