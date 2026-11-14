"""How far a job is kept from its node (docs/design.md, Isolation per job, M23.1).

`isolation: container` in `.mulebox.yml` runs each job in a fresh confined container
(worker/isolated.py). It travels as a need, `isolated`, which a Linux worker with Docker offers
by itself, so a worker that cannot give it never claims such a job, and no wire or store change
is needed. A project's own image (`image:`) travels in the job's `env` under `IMAGE_KEY`, as the
compose files do (common/compose.py); the worker takes it out before the job sees its values.
"""

from __future__ import annotations

import re
import sys

CAPABILITY = "isolated"
NONE, CONTAINER = "none", "container"
LEVELS = (NONE, CONTAINER)
IMAGE_KEY = "MULEBOX_JOB_IMAGE"
# A Docker image reference: [registry/]name[:tag][@digest], lowercase name parts.
_IMAGE_RE = re.compile(r"[a-z0-9][a-z0-9._-]*(?::[0-9]+)?(?:/[a-z0-9._-]+)*"
                       r"(?::[A-Za-z0-9_][A-Za-z0-9._-]{0,127})?(?:@sha256:[0-9a-f]{64})?")
MAX_IMAGE = 255


def level_problem(level: object) -> str | None:
    """Why `level` is not an isolation level, or None."""
    if level not in LEVELS:
        return f"must be one of {', '.join(LEVELS)}"
    return None


def image_problem(reference: object) -> str | None:
    """Why `reference` cannot be a job's image, or None."""
    if not isinstance(reference, str) or not reference or len(reference) > MAX_IMAGE:
        return f"must be an image name of at most {MAX_IMAGE} characters"
    if reference.startswith("-") or not _IMAGE_RE.fullmatch(reference):
        return "must be a Docker image name, such as ubuntu:24.04 or ghcr.io/example/ci:1"
    return None


def offered(configured: tuple[str, ...], docker_capability: str,
            platform: str = sys.platform) -> tuple[str, ...]:
    """`isolated` for a Linux worker with Docker: on a Mac an Apple build cannot run in a
    container, and a Linux one there is a later step (design.md)."""
    return (CAPABILITY,) if docker_capability in configured and platform.startswith("linux") else ()
