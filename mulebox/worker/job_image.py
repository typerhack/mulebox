"""mulebox's own image for isolated jobs (docs/design.md, Isolation per job).

Built once per node, by the first isolated job that needs it, from the node's own system
(Ubuntu or Debian, the release in /etc/os-release), so the toolchains the node installed for
jobs (toolchains.py) run in it from their read-only mount. It holds what a build commonly
needs and nothing of the node. The tag carries a digest of the Dockerfile, so a change here
builds a new image rather than reusing a stale one; old tags stay as cache, like pulled images.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

REPOSITORY = "mulebox-job"
LABEL = "mulebox.image"  # value "job": made by mulebox, never removed by a job's cleanup
FALLBACK_BASE = "ubuntu:24.04"
_RELEASE = re.compile(r"[0-9][0-9.]{0,15}")
PACKAGES = ("bash", "build-essential", "ca-certificates", "curl", "git", "jq", "pkg-config",
            "python3", "python3-pip", "python3-venv", "tzdata", "unzip", "xz-utils", "zip")


def base_image(os_release: Path = Path("/etc/os-release")) -> str:
    """The node's own system as an image name: what its toolchains were built to run on."""
    try:
        text = os_release.read_text(encoding="utf-8")
    except OSError:
        return FALLBACK_BASE
    fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    name = fields.get("ID", "").strip('"')
    release = fields.get("VERSION_ID", "").strip('"')
    if name in ("ubuntu", "debian") and _RELEASE.fullmatch(release):
        return f"{name}:{release}"
    return FALLBACK_BASE


def dockerfile(base: str) -> str:
    return (f"FROM {base}\n"
            f"LABEL {LABEL}=job\n"
            "ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8\n"
            "RUN apt-get update && apt-get install -y --no-install-recommends "
            f"{' '.join(PACKAGES)} && rm -rf /var/lib/apt/lists/*\n")


def tag(text: str) -> str:
    return f"{REPOSITORY}:{hashlib.sha256(text.encode()).hexdigest()[:12]}"
