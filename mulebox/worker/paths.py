"""Named worker roots (jobs, cache, staging, runners) next to the checked `Roots`.

`safepath.Roots` is an unnamed tuple of resolved folders, and `ensure_dir` only accepts
paths spelled under those resolved folders. The worker needs to know which root is which,
so `NodePaths` keeps both: the checked `Roots` and each named root resolved the same way.
It also owns the job folder layout from docs/interfaces-m1.md (Filesystem layout).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from mulebox.common.config_reader import NAME_RE
from mulebox.common.ids import is_valid_id
from mulebox.common.safepath import Roots, UnsafePath


@dataclass(frozen=True)
class NodePaths:
    roots: Roots
    jobs: Path
    cache: Path
    staging: Path
    runners: Path

    @classmethod
    def from_config(cls, roots: dict[str, str]) -> NodePaths:
        """Build from NodeConfig.roots; every root is checked by `Roots.from_config`."""
        checked = Roots.from_config(roots)
        named = {key: Path(os.path.realpath(roots[key])) for key in
                 ("jobs", "cache", "staging", "runners")}
        return cls(roots=checked, **named)

    def project_dir(self, project: str) -> Path:
        if not isinstance(project, str) or not NAME_RE.fullmatch(project):
            raise UnsafePath(f"project name {project!r} is not a safe folder name")
        return self.jobs / project

    def job_dir(self, project: str, job_id: str) -> Path:
        if not is_valid_id(job_id, "job"):
            raise UnsafePath(f"job id {job_id!r} is not a valid mulebox job id")
        return self.project_dir(project) / job_id

    def browsers_dir(self) -> Path:
        return self.cache / "playwright"

    def toolchains_dir(self) -> Path:
        return self.cache / "toolchains"
