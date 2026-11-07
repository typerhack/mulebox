"""What a project's own CI and compose files say, for `mulebox init` (init_detect.py).

A first job should test what CI tests, so these come before any guess:

- `ci_compose_files`: the compose files CI runs with, from `COMPOSE_FILE: a.yml:b.yml` or
  `docker compose -f a.yml -f b.yml` in `.github/workflows/`. The list used most often wins, the
  first one seen on a tie; a list naming a file the project does not have is skipped.
- `ci_node_version`: `node-version:` of `actions/setup-node`, exact or not.
- `services_by_folder`: which compose service is built from a folder (`build: ./api`), so that
  folder's tools run in its image with `docker compose exec`, not on the machine.
- `newest_node(major)`: the newest release of a Node major from nodejs.org, as only an exact
  version can be pinned. A network failure gives None; init then says what to pin.

Only files are read, and nodejs.org's release list asked for; nothing of the project runs.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from mulebox.common.download import DownloadError, fetch_json

NODE_INDEX = "https://nodejs.org/dist/index.json"
INDEX_TIMEOUT_S = 10
_COMPOSE_FILE = re.compile(r"\bCOMPOSE_FILE:\s*['\"]?([^\s'\"#]+)")
_COMPOSE_F = re.compile(r"docker[ -]compose((?:\s+(?:-f|--file)\s+\S+)+)")
_FILE_ARG = re.compile(r"(?:-f|--file)\s+(\S+)")
_NODE = re.compile(r"\bnode-version:\s*['\"]?([0-9][0-9.x]*)")
_PREFERRED = ("app", "api", "php", "backend", "web")  # several services from one folder


def _workflows(root: Path) -> list[str]:
    folder = root / ".github" / "workflows"
    try:
        files = sorted(p for p in folder.iterdir() if p.suffix in (".yml", ".yaml"))
    except OSError:
        return []
    texts = []
    for path in files:
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return texts


def ci_compose_files(root: Path) -> list[str]:
    lists: list[tuple[str, ...]] = []
    for text in _workflows(root):
        lists += [tuple(m.split(":")) for m in _COMPOSE_FILE.findall(text)]
        lists += [tuple(_FILE_ARG.findall(m)) for m in _COMPOSE_F.findall(text)]
    usable = [names for names in lists
              if names and all((root / name).is_file() for name in names)]
    if not usable:
        return []
    counts = Counter(usable)
    best = max(counts.values())
    return list(next(names for names in usable if counts[names] == best))


def ci_node_version(root: Path) -> str | None:
    for text in _workflows(root):
        if found := _NODE.search(text):
            return found.group(1)
    return None


def _services(root: Path, files: list[str]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for name in files:
        try:
            data = yaml.safe_load((root / name).read_text(encoding="utf-8")) or {}
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue
        services = data.get("services") if isinstance(data, dict) else None
        for service, spec in (services or {}).items():
            if isinstance(spec, dict):
                merged.setdefault(service, {}).update(spec)
    return merged


def _context(spec: dict[str, Any]) -> str | None:
    build = spec.get("build")
    if isinstance(build, str):
        return build
    if isinstance(build, dict) and isinstance(build.get("context"), str):
        return build["context"]
    return None


def services_by_folder(root: Path, files: list[str]) -> dict[Path, str]:
    """Folder -> the service built from it; of several, a usual app name, else the first."""
    found: dict[Path, list[str]] = {}
    for service, spec in _services(root, files).items():
        context = _context(spec)
        if context is not None:
            found.setdefault((root / context).resolve(), []).append(service)
    return {folder: next((s for s in _PREFERRED if s in names), names[0])
            for folder, names in found.items()}


def newest_node(major: int) -> str | None:
    try:
        releases = fetch_json(NODE_INDEX, timeout_s=INDEX_TIMEOUT_S)
    except DownloadError:
        return None
    versions = [r.get("version", "").lstrip("v") for r in releases if isinstance(r, dict)]
    same = [v for v in versions if re.fullmatch(rf"{major}\.\d+\.\d+", v)]
    return max(same, key=lambda v: tuple(int(p) for p in v.split(".")), default=None)
