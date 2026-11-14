"""How far a job is kept from its node (docs/design.md, Isolation per job, M23.1).

`isolation: container` in `.mulebox.yml` runs each job in a fresh confined container
(worker/isolated.py). It travels as a need, `isolated`, which a Linux worker with Docker offers
by itself, so a worker that cannot give it never claims such a job, and no wire or store change
is needed.

A node sets a floor, `isolation = "container"` in its node.toml: every job there runs isolated,
whatever `.mulebox.yml` says, and a project cannot go below it. A project that writes
`isolation: none` asks for that, and it travels as the need `unisolated`, which only a node
whose floor is `none` offers; so such a job never lands on an isolated node, and with none to
run it the coordinator refuses it at once and says why (coordinator/needs.py). A project that
says nothing takes the node's floor.

A project's own image (`image:`) travels in the job's `env` under `IMAGE_KEY`, as the compose
files do (common/compose.py); the worker takes it out before the job sees its values.
"""

from __future__ import annotations

import re
import sys

CAPABILITY = "isolated"
UNISOLATED = "unisolated"  # asked by `isolation: none`; offered where the floor is `none`
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


def can_isolate(configured: tuple[str, ...], docker_capability: str,
                platform: str | None = None) -> bool:
    """A Linux worker with Docker: on a Mac an Apple build cannot run in a container, and a
    Linux one there is a later step (design.md). `platform`: this one's by default."""
    return docker_capability in configured and (platform or sys.platform).startswith("linux")


def offered(configured: tuple[str, ...], docker_capability: str,
            platform: str | None = None, floor: str = NONE) -> tuple[str, ...]:
    """What a worker offers by itself: `isolated` if it can isolate, `unisolated` unless its
    floor is `container`."""
    found = (CAPABILITY,) if can_isolate(configured, docker_capability, platform) else ()
    return (*found, *((UNISOLATED,) if floor == NONE else ()))
