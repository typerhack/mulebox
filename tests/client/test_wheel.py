"""The wheel `mulebox setup` sends is one pip accepts, and holds what a machine needs."""

import subprocess
import sys
import zipfile

from mulebox.client import wheel
from mulebox.version import source_version


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
