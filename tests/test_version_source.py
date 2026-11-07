"""The version a checkout reports is its VERSION file, never stale editable metadata."""

from pathlib import Path

from mulebox import version


def test_a_checkout_reports_its_version_file_even_if_its_metadata_lags(monkeypatch):
    monkeypatch.setattr(version.metadata, "version", lambda name: "0.0.1")
    root = Path(version.__file__).resolve().parent.parent
    assert version.get_version() == (root / "VERSION").read_text().strip()


def test_an_installed_package_reads_its_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(version, "_ROOT", tmp_path)
    monkeypatch.setattr(version, "_VERSION_FILE", tmp_path / "VERSION")
    monkeypatch.setattr(version.metadata, "version", lambda name: "1.2.3")
    assert version.get_version() == "1.2.3"
