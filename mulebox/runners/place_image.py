"""The image an isolated runner's containers start from (design.md, Runners for public
repositories).

GitHub's own runner image, `ghcr.io/actions/actions-runner:<version>`, with what a workflow
needs before its first step: git (actions/checkout without it fetches a tarball, with no
history), curl, shellcheck and the archivers setup actions unpack with. `/opt/hostedtoolcache`
belongs to the runner's user, so the tool cache volume a place mounts there starts writable.
Built once on the node and tagged by the runner version and this recipe, so a job starts in
seconds; a new runner release or a changed recipe builds a new tag. Older tags stay as cache
until the owner removes them.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from mulebox.common.ids import new_ulid
from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.worker.docker import Docker, DockerError
from mulebox.worker.paths import NodePaths

BASE = "ghcr.io/actions/actions-runner"
NAME = "mulebox-runner"
BUILD_TIMEOUT_S = 1800.0
TOOL_CACHE = "/opt/hostedtoolcache"
DOCKERFILE = """FROM {base}:{version}
USER root
RUN apt-get update \\
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \\
      git curl ca-certificates shellcheck xz-utils unzip zstd \\
 && rm -rf /var/lib/apt/lists/* \\
 && mkdir -p {tools} && chown runner:runner {tools}
USER runner
"""


def recipe(version: str) -> str:
    return DOCKERFILE.format(base=BASE, version=version, tools=TOOL_CACHE)


def tag(version: str) -> str:
    digest = hashlib.sha256(recipe(version).encode()).hexdigest()[:12]
    return f"{NAME}:{version}-{digest}"


def present(docker: Docker, image: str) -> bool:
    try:
        docker.run("image", "inspect", "--format", "{{.Id}}", image)
        return True
    except DockerError:
        return False


def ensure(docker: Docker, paths: NodePaths, version: str) -> str:
    """The image for this runner version, built when missing; its tag."""
    image = tag(version)
    if present(docker, image):
        return image
    work = ensure_dir(paths.staging / "tmp", paths.roots) / f"runner-image-{new_ulid()}"
    try:
        ensure_dir(work, paths.roots)
        dockerfile = Path(work) / "Dockerfile"
        fd = os.open(dockerfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(recipe(version))
        docker.run("build", "--pull", "--tag", image, "--label", "mulebox.runner-image=1",
                   str(work), timeout_s=BUILD_TIMEOUT_S)
    finally:
        remove_tree(work, paths.roots)
    return image
