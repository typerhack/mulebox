"""The version has one source: the VERSION file at the repository root.

An installed package reads it from its metadata (setuptools copies VERSION there at build
time). A source checkout that is not installed falls back to reading the file directly.
"""

from importlib import metadata
from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def get_version() -> str:
    try:
        return metadata.version("mulebox")
    except metadata.PackageNotFoundError:
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
