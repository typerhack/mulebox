"""safepath Roots: which folders may be roots, and how they are resolved."""

import os
from pathlib import Path

import pytest

from mulebox.common.errors import MuleboxError
from mulebox.common.safepath import PathOutsideRoots, RemovalDenied, Roots, UnsafePath


def test_errors_are_mulebox_errors():
    assert issubclass(PathOutsideRoots, MuleboxError)
    assert issubclass(UnsafePath, MuleboxError)
    assert issubclass(RemovalDenied, UnsafePath)


def test_roots_are_resolved(tmp_path, root):
    (tmp_path / "link").symlink_to(root)
    assert Roots((tmp_path / "link",)).paths == (root,)
    assert Roots((str(root),)).paths == (root,)


def test_from_config(tmp_path, root):
    cache = tmp_path / "cache"
    cache.mkdir()
    built = Roots.from_config({"jobs": str(root), "cache": str(cache)})
    assert built.paths == (root, cache)


@pytest.mark.parametrize("value", ["", "relative/jobs", None])
def test_from_config_rejects_bad_values(value):
    with pytest.raises(UnsafePath, match="'jobs'"):
        Roots.from_config({"jobs": value})


def test_from_config_rejects_empty():
    with pytest.raises(UnsafePath):
        Roots.from_config({})


@pytest.mark.parametrize("bad", ["/", "/usr", "/etc", "/bin", "/var", "/home", "/tmp", "/dev"])
def test_system_roots_rejected(bad):
    if not os.path.isdir(bad):
        pytest.skip(f"{bad} does not exist here")
    with pytest.raises(UnsafePath):
        Roots((Path(bad),))


def test_home_and_its_parents_rejected(tmp_path, monkeypatch):
    home = tmp_path / "home" / "alice"
    (home / "mulebox").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    for bad in (home, home.parent, tmp_path):
        with pytest.raises(UnsafePath, match="protected"):
            Roots((bad,))
    assert Roots((home / "mulebox",)).paths == (home / "mulebox",)


def test_root_must_be_absolute_existing_directory(tmp_path):
    (tmp_path / "file").write_text("x")
    for bad in (Path("jobs"), tmp_path / "missing", tmp_path / "file"):
        with pytest.raises(UnsafePath):
            Roots((bad,))
    with pytest.raises(UnsafePath):
        Roots(())


def test_overlapping_roots_rejected(root):
    (root / "inner").mkdir()
    with pytest.raises(UnsafePath, match="overlap"):
        Roots((root, root / "inner"))
    with pytest.raises(UnsafePath, match="overlap"):
        Roots((root, root))
