"""A GitHub runner's size: the cores and memory one of its runs counts as on its node
(docs/design.md, Job sizes; common/job_size.py).

Kept in the runner's `.mulebox-runner.json` as `size`; the job-started hook sends it with each
reservation (hooks.py), so a change counts from the next run, with no restart. With none, a run
counts as one of the node's slots, as a mulebox job with no size does.

    mulebox runner size <runner> --cores 6 --memory 8GB
    mulebox runner size <runner> --off
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mulebox.common import job_size
from mulebox.runners import layout
from mulebox.runners.names import RunnerUsageError
from mulebox.worker.paths import NodePaths


def asked(cores: float | None, memory: str | None) -> dict[str, Any] | None:
    """The size from `--cores` and `--memory`, checked; None for neither."""
    if cores is None and memory is None:
        return None
    try:
        return job_size.checked({"cores": cores, "memory": memory})
    except ValueError as exc:
        raise RunnerUsageError(str(exc).replace("size.", "--")) from None


def argv(size: dict[str, Any] | None) -> list[str]:
    """`--cores` and `--memory` for a `runner add` on the node."""
    if not size:
        return []
    out = ["--cores", f"{size['cores']:g}"] if "cores" in size else []
    return out + (["--memory", f"{size['memory'] / 10**6:g}MB"] if "memory" in size else [])


def store(paths: NodePaths, runner: str, size: dict[str, Any] | None) -> None:
    """Keep `size` for `runner` (None: take it away)."""
    folder = layout.runner_dir(paths, runner)
    if not folder.is_dir():
        raise RunnerUsageError(f"no runner named {runner} on this node (`mulebox runner list`)")
    meta = {k: v for k, v in layout.read_meta(folder).items() if k != "size"}
    layout.write_meta(paths, folder, {**meta, **({"size": size} if size else {})})


def of(folder: Path) -> dict[str, Any] | None:
    """The size kept in a runner's folder, or None (none, or one that does not read)."""
    try:
        return job_size.checked(layout.read_meta(folder).get("size"))
    except (ValueError, OSError):
        return None
