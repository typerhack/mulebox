"""A wheel of the mulebox that is running, for `mulebox setup` to send to a node.

Built from the package's own files, so it works the same from a checkout, a pip install or a
future one-line install, and needs no build tool. The dependencies come from the installed
metadata; the version from `version.source_version`. From a checkout the dashboard's React front
end is built first when it is out of date (webbuild.py).
"""

import base64
import hashlib
import zipfile
from importlib import metadata
from pathlib import Path

import mulebox
from mulebox.client import webbuild
from mulebox.version import source_version

_TAG = "py3-none-any"
_WHEEL = f"Wheel-Version: 1.0\nGenerator: mulebox\nRoot-Is-Purelib: true\nTag: {_TAG}\n"
_ENTRY_POINTS = "[console_scripts]\nmulebox = mulebox.cli:main\n"


# What runs before the package's files are read; a name of its own so tests can leave Node out.
_prepare = webbuild.ensure


def _record_line(name: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{name},sha256={digest},{len(data)}"


def _metadata_text(version: str) -> str:
    needs = [item for item in metadata.requires("mulebox") or [] if "extra ==" not in item]
    lines = ["Metadata-Version: 2.1", "Name: mulebox", f"Version: {version}",
             f"Requires-Python: {metadata.metadata('mulebox')['Requires-Python']}",
             *(f"Requires-Dist: {item}" for item in needs)]
    return "\n".join(lines) + "\n"


def _package_files(package: Path) -> list[Path]:
    return sorted(path for path in package.rglob("*")
                  if path.is_file() and "__pycache__" not in path.parts
                  and not path.name.startswith("."))


def build(out_dir: Path) -> Path:
    """Write the wheel into `out_dir`; return its path."""
    package = Path(mulebox.__file__).resolve().parent
    _prepare(package)
    version = source_version()
    info = f"mulebox-{version}.dist-info"
    target = out_dir / f"mulebox-{version}-{_TAG}.whl"
    extra = {f"{info}/METADATA": _metadata_text(version).encode(),
             f"{info}/WHEEL": _WHEEL.encode(),
             f"{info}/entry_points.txt": _ENTRY_POINTS.encode()}
    record = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as wheel:
        for path in _package_files(package):
            name = f"mulebox/{path.relative_to(package).as_posix()}"
            data = path.read_bytes()
            wheel.writestr(name, data)
            record.append(_record_line(name, data))
        for name, data in extra.items():
            wheel.writestr(name, data)
            record.append(_record_line(name, data))
        wheel.writestr(f"{info}/RECORD", "\n".join([*record, f"{info}/RECORD,,"]) + "\n")
    return target
