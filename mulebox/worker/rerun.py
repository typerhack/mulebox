"""A rerun on this worker: whether the kept job still holds, and the claim it runs as
(docs/design.md, Rerun from the failed stage; kept.py keeps them).

A rerun skips `images` and `services` (its containers are up) and the stages before the one
asked: `--from-stage setup` skips `install`, `--from-stage command` skips both. It cannot when
nothing is kept, when what the skipped stages depend on changed (the compose files, the
Dockerfiles and lockfiles project_home.py reads, the `setup` and `install` lines, the toolchain,
the env), or when a kept container stopped. Then it runs from the start, and says why.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from mulebox.common.status import COMMAND, INSTALL
from mulebox.worker import kept as kept_jobs
from mulebox.worker import project_home
from mulebox.worker.docker import Docker
from mulebox.worker.kept import Kept

CHANGED = ("something the skipped stages depend on changed (compose files, a Dockerfile, a "
           "lockfile, setup or install, the toolchain or env)")


def key(tree: Path, claim: dict[str, Any]) -> str:
    """What the stages a rerun skips depend on, before `setup` or `install` is skipped."""
    both = project_home.install_key(tree, claim) + project_home.setup_key(tree, claim)
    return hashlib.sha256(both.encode()).hexdigest()


def problem(kept: Kept | None, claim: dict[str, Any], tree: Path, docker: Docker | None
            ) -> str | None:
    """Why this rerun cannot use what was kept, or None."""
    if kept is None:
        return "nothing is kept on this node for it any more"
    if kept.key != key(tree, claim):
        return CHANGED
    if docker is None:
        return "this node has no Docker"
    return kept_jobs.stopped(docker, kept.home)


def as_run(claim: dict[str, Any]) -> dict[str, Any]:
    """The claim without the stages before `from_stage`."""
    stage = claim.get("from_stage")
    out = dict(claim)
    if stage != INSTALL:
        out["install"] = None
    if stage == COMMAND:
        out["setup"] = None
    return out


def note(kept: Kept, claim: dict[str, Any]) -> str:
    """The log line of a rerun; it names only the stages the job has and skips."""
    stage, skipped = claim["from_stage"], ["images", "services"]
    if stage != INSTALL and claim.get("install"):
        skipped.append("install")
    if stage == COMMAND and claim.get("setup"):
        skipped.append("setup")
    return (f"mulebox: rerun from {stage} with the containers of {kept.home} "
            f"({', '.join(skipped)} skipped)\n")


def fallback_note(why: str) -> str:
    return f"mulebox: cannot rerun from the kept job: {why}; running from the start\n"
