"""What `mulebox init` found, and the small readers its detectors share."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

IN_SERVICE = "docker compose exec"  # a command already inside a compose service


@dataclass
class Detected:
    project: str
    toolchain: dict[str, str] = field(default_factory=dict)
    needs: list[str] = field(default_factory=list)
    compose: list[str] = field(default_factory=list)
    install: list[str] = field(default_factory=list)  # runs in a service, after `compose:`
    setup: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)  # all of them make the job `check`
    jobs: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    services: dict[Path, str] = field(default_factory=dict)  # folder -> service built from it


def text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(text(path) or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}
