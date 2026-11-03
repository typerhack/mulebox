"""The GitHub Actions runner package: find the latest release, download, verify, extract.

- `latest_release(arch)`: asks `api.github.com/repos/actions/runner/releases/latest`
  (no token needed) and picks the `actions-runner-linux-<arch>-<version>.tar.gz` asset.
  Its SHA-256 comes from the release body, between `<!-- BEGIN SHA linux-<arch> -->` and
  `<!-- END SHA linux-<arch> -->`; a release without that checksum is refused.
- `fetch_verified(paths, release)`: the tarball, cached as
  `<cache>/actions-runner/<asset>` and verified on every use; a cached file that no
  longer matches is removed and downloaded again. Downloads go to a temporary name and
  are renamed into place only after the checksum matched.
- `extract(paths, tarball, dest)`: safe extraction through `worker/archive.py`.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mulebox.common import download
from mulebox.common.errors import MuleboxError
from mulebox.common.ids import new_ulid
from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.worker.archive import extract_tar
from mulebox.worker.paths import NodePaths

LATEST_URL = "https://api.github.com/repos/actions/runner/releases/latest"
API_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
DOWNLOAD_PREFIX = "https://github.com/actions/runner/releases/download/"
CACHE_DIR = "actions-runner"
ARCHES = ("x64", "arm64")
_VERSION_RE = re.compile(r"\d{1,4}\.\d{1,4}\.\d{1,4}")
_SHA_RE = re.compile(r"[0-9a-f]{64}")

FetchJson = Callable[[str], Any]
FetchFile = Callable[[str, Path], None]


class ReleaseError(MuleboxError):
    """The runner release could not be found, downloaded or verified."""


@dataclass(frozen=True)
class Release:
    version: str
    asset: str
    url: str
    sha256: str


def _api_json(url: str) -> Any:
    return download.fetch_json(url, API_HEADERS)


def body_sha(body: str, arch: str) -> str:
    """The checksum between the release body's BEGIN/END SHA markers for linux-<arch>."""
    key = re.escape(f"linux-{arch}")
    match = re.search(rf"<!--\s*BEGIN SHA {key}\s*-->\s*([0-9A-Fa-f]{{64}})\s*"
                      rf"<!--\s*END SHA {key}\s*-->", body)
    if match is None:
        raise ReleaseError(f"the runner release notes carry no SHA-256 for linux-{arch}")
    return match.group(1).lower()


def parse_release(data: Any, arch: str) -> Release:
    """Pick the linux-<arch> tarball and its checksum from a `releases/latest` reply."""
    if arch not in ARCHES:
        raise ReleaseError(f"no runner build for linux-{arch}; known: {', '.join(ARCHES)}")
    if not isinstance(data, dict):
        raise ReleaseError("the runner release reply is not a JSON object")
    tag = data.get("tag_name")
    version = tag[1:] if isinstance(tag, str) and tag.startswith("v") else tag
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise ReleaseError(f"the runner release has an unexpected tag {tag!r}")
    asset = f"actions-runner-linux-{arch}-{version}.tar.gz"
    url = None
    for item in data.get("assets") or []:
        if isinstance(item, dict) and item.get("name") == asset:
            url = item.get("browser_download_url")
    if not isinstance(url, str) or not url.startswith(DOWNLOAD_PREFIX):
        raise ReleaseError(f"runner release {version} has no download for {asset}")
    body = data.get("body")
    return Release(version, asset, url, body_sha(body if isinstance(body, str) else "", arch))


def latest_release(arch: str | None = None, fetch_json: FetchJson = _api_json) -> Release:
    try:
        arch = arch or download.linux_arch()
        return parse_release(fetch_json(LATEST_URL), arch)
    except download.DownloadError as exc:
        raise ReleaseError(f"cannot look up the latest runner release: {exc}") from exc


def _matches(path: Path, expected: str) -> bool:
    return path.is_file() and download.sha256_file(path) == expected


def fetch_verified(paths: NodePaths, release: Release,
                   fetch: FetchFile = download.fetch_file) -> Path:
    """The verified tarball in the cache; downloaded when missing or not matching."""
    if not _SHA_RE.fullmatch(release.sha256):
        raise ReleaseError(f"{release.asset}: invalid expected SHA-256")
    cache = ensure_dir(paths.cache / CACHE_DIR, paths.roots)
    final = cache / release.asset
    if _matches(final, release.sha256):
        return final
    if final.exists() or final.is_symlink():
        remove_tree(final, paths.roots)
    part = cache / f".part-{new_ulid()}"
    try:
        try:
            fetch(release.url, part)
        except download.DownloadError as exc:
            raise ReleaseError(str(exc)) from exc
        actual = download.sha256_file(part)
        if actual != release.sha256:
            raise ReleaseError(f"{release.asset}: sha256 {actual} does not match the "
                               f"{release.sha256} published in the release notes; refusing it")
        os.replace(part, final)
    finally:
        remove_tree(part, paths.roots)
    return final


def extract(paths: NodePaths, tarball: Path, dest: Path) -> Path:
    """Extract a runner tarball into dest (created inside the roots)."""
    return extract_tar(tarball, dest, paths.roots)
