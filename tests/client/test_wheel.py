"""The wheel `mulebox setup` sends is one pip accepts, and holds what a machine needs."""

import subprocess
import sys
import zipfile

from pathlib import Path

import pytest

import mulebox
from mulebox.client import wheel
from mulebox.version import source_version


@pytest.fixture(autouse=True)
def prepared(monkeypatch):
    """No Node in these tests: the web build before a wheel has its own (test_webbuild.py)."""
    asked = []
    monkeypatch.setattr(wheel, "_prepare", asked.append)
    return asked


def test_the_web_front_end_is_looked_at_before_the_files_are_read(tmp_path, prepared):
    wheel.build(tmp_path)
    assert prepared == [Path(mulebox.__file__).resolve().parent]


def test_the_wheel_holds_code_installer_and_metadata(tmp_path):
    built = wheel.build(tmp_path)
    assert built.name == f"mulebox-{source_version()}-py3-none-any.whl"
    names = zipfile.ZipFile(built).namelist()
    assert "mulebox/cli.py" in names
    assert "mulebox/machine/install.sh" in names
    assert "mulebox/machine/systemd/mulebox-worker.service" in names
    assert "mulebox/dashboard/static/style.css" in names or any(
        name.startswith("mulebox/dashboard/static/") for name in names)
    assert not [name for name in names if "__pycache__" in name or name.endswith(".pyc")]


def test_pip_installs_it(tmp_path):
    built = wheel.build(tmp_path)
    target = tmp_path / "site"
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "--no-index",
                    "--disable-pip-version-check", "--target", str(target), str(built)],
                   check=True, capture_output=True)
    info = next(target.glob("mulebox-*.dist-info"))
    assert (target / "mulebox" / "cli.py").is_file()
    text = (info / "METADATA").read_text()
    assert f"Version: {source_version()}" in text and "Requires-Dist: PyYAML" in text
    assert (target / "bin" / "mulebox").is_file()
