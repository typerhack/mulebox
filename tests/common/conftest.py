"""Shared fixtures: a root and an outside folder, both under tmp_path."""

import pytest

from mulebox.common.safepath import Roots


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "jobs"
    path.mkdir()
    return path


@pytest.fixture
def roots(root):
    return Roots((root,))


@pytest.fixture
def outside(tmp_path):
    path = tmp_path / "outside"
    (path / "sub").mkdir(parents=True)
    (path / "keep.txt").write_text("keep")
    (path / "sub" / "keep.txt").write_text("keep")
    return path
