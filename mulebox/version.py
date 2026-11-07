"""The version has one source: the VERSION file at the repository root.

A source checkout, editable install or not, reads that file: an editable install's metadata
keeps the version it was installed at, so it would lag behind every bump and make a laptop
and a build machine on the same commit look like different versions. An installed package
has no checkout around it and reads its metadata (setuptools copies VERSION there at build
time).
"""

from importlib import metadata
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_VERSION_FILE = _ROOT / "VERSION"


def _in_checkout() -> bool:
    return _VERSION_FILE.is_file() and (_ROOT / "pyproject.toml").is_file()


def source_version() -> str:
    """The VERSION file of a checkout (used to build a wheel from it)."""
    return get_version()


def get_version() -> str:
    if _in_checkout():
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    try:
        return metadata.version("mulebox")
    except metadata.PackageNotFoundError:
        return "unknown"
