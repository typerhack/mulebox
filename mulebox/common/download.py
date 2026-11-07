"""HTTPS downloads and checksums shared by toolchain and runner installs.

- `fetch_file(url, dest)`: stream a URL into a new file (`dest` must not exist).
- `fetch_json(url)`: a small JSON document (API replies), with a size cap.
- `sha256_file(path)`: hex digest of a file.
- `linux_arch(machine)`: the `x64` / `arm64` name used by Node and GitHub release assets.

Errors raise DownloadError; callers wrap it in their own error type if they need one.
"""

from __future__ import annotations

import hashlib
import json
import http.client
import platform
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from mulebox.common.errors import MuleboxError

HTTP_TIMEOUT_S = 60
JSON_MAX_BYTES = 4 * 1024 * 1024
USER_AGENT = "mulebox"
_ARCH = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}


class DownloadError(MuleboxError):
    """A download failed, or its content is not what was expected."""


class NetworkLost(DownloadError):
    """The network or the server failed: the same download can work later. A server's refusal,
    such as a version that does not exist, is a plain DownloadError."""


def _failure(what: str, exc: Exception) -> DownloadError:
    refused = isinstance(exc, urllib.error.HTTPError) and exc.code < 500
    return (DownloadError if refused else NetworkLost)(f"{what} failed: {exc}")


def _request(url: str, headers: dict[str, str] | None) -> urllib.request.Request:
    if not url.startswith("https://"):
        raise DownloadError(f"refusing to download {url!r}: only https URLs are allowed")
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})


def fetch_file(url: str, dest: Path, headers: dict[str, str] | None = None) -> None:
    """Download url into dest, which is created (it must not exist yet)."""
    try:
        with urllib.request.urlopen(_request(url, headers), timeout=HTTP_TIMEOUT_S) as resp, \
                open(dest, "xb") as fh:
            while block := resp.read(1 << 20):
                fh.write(block)
    except (OSError, http.client.HTTPException) as exc:
        raise _failure(f"download of {url}", exc) from exc


def fetch_json(url: str, headers: dict[str, str] | None = None) -> Any:
    """Fetch and parse a JSON document of at most JSON_MAX_BYTES."""
    try:
        with urllib.request.urlopen(_request(url, headers), timeout=HTTP_TIMEOUT_S) as resp:
            data = resp.read(JSON_MAX_BYTES + 1)
    except (OSError, http.client.HTTPException) as exc:
        raise _failure(f"request to {url}", exc) from exc
    if len(data) > JSON_MAX_BYTES:
        raise DownloadError(f"reply from {url} is larger than {JSON_MAX_BYTES} bytes")
    try:
        return json.loads(data)
    except ValueError as exc:
        raise DownloadError(f"reply from {url} is not JSON: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def linux_arch(machine: str | None = None) -> str:
    """`x64` or `arm64` for this (or the given) CPU; DownloadError for anything else."""
    machine = (machine or platform.machine()).lower()
    if machine not in _ARCH:
        raise DownloadError(f"no build for CPU architecture {machine!r}")
    return _ARCH[machine]
