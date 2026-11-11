"""The version has one source: the VERSION file at the repository root.

A source checkout, editable install or not, reads that file: an editable install's metadata
keeps the version it was installed at, so it would lag behind every bump and make a laptop
and a build machine on the same commit look like different versions. An installed package
has no checkout around it and reads its metadata (setuptools copies VERSION there at build
time).
"""

from functools import cache
from importlib import metadata
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_VERSION_FILE = _ROOT / "VERSION"


def in_checkout() -> bool:
    return _VERSION_FILE.is_file() and (_ROOT / "pyproject.toml").is_file()


def source_version() -> str:
    """The VERSION file of a checkout (used to build a wheel from it)."""
    return get_version()


def get_version() -> str:
    if in_checkout():
        return _VERSION_FILE.read_text(encoding="utf-8").strip()
    return _installed_version()


@cache
def _installed_version() -> str:
    """An installed package's version, read once: it cannot change under a running process, and
    the dashboard asks for it every second (reading metadata cost about 1 ms each time)."""
    try:
        return metadata.version("mulebox")
    except metadata.PackageNotFoundError:
        return "unknown"
