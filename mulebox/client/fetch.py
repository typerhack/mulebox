"""Files a job kept, brought to the dev machine (docs/design.md, Files back).

`with_keep` adds `--keep` to a job's own `keep:`. `fetch` downloads a finished job's pack
(`rpc-download-files`) next to where it goes, unpacks it through the same safe unpacking as a
snapshot (common/archive.py: no absolute names, no `..`, no links out), and only then puts it in
place, so a failed fetch leaves an earlier one as it was. The place is always a folder of the
job's own, `<dir>/<job>/` with `-o <dir>`, else `.mulebox/files/<job>/` in the project: mulebox makes `.mulebox/` with a `.gitignore` of `*`, so
git leaves it out, and snapshots never send it (client/excludes.py).
"""

from __future__ import annotations

import dataclasses
import os
import tempfile
from pathlib import Path
from typing import Any, TextIO

from mulebox.client import report
from mulebox.common import keep_files
from mulebox.common.archive import extract_tar
from mulebox.common.config import ProjectConfig
from mulebox.common.errors import MuleboxError
from mulebox.common.safepath import Roots, ensure_dir, remove_tree


class FetchError(MuleboxError):
    error_code = "usage.invalid"


def with_keep(project: ProjectConfig, more: tuple[str, ...]) -> ProjectConfig:
    """`project` with `--keep` entries after its own `keep:`; FetchError for a bad one."""
    if not more:
        return project
    try:
        entries = keep_files.checked((*project.keep, *more))
    except ValueError as exc:
        raise FetchError(f"--{exc}", fix="name a file, folder or pattern inside the project, "
                         "such as --keep test-results/") from None
    return dataclasses.replace(project, keep=entries)


def own_folder(root: Path) -> Path:
    """`<project>/.mulebox`, made with a `.gitignore` of `*` so git leaves it all out."""
    folder = root / keep_files.FOLDER
    folder.mkdir(mode=0o755, exist_ok=True)
    if folder.is_symlink() or not folder.is_dir():
        raise FetchError(f"{folder} is not a folder of mulebox's own")
    ignore = folder / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    return folder


def target_for(root: Path, job_id: str, out_dir: Path | None) -> Path:
    """`<out_dir>/<job>/`, or `.mulebox/files/<job>/`: always a folder of the job's own, as a
    fetch replaces it whole."""
    base = out_dir if out_dir is not None else own_folder(root) / keep_files.FILES_DIR
    return base / job_id


def fetch(remote: Any, job_id: str, status: dict[str, Any], target: Path, err: TextIO) -> int:
    """Bring the job's kept files into `target` (replacing an earlier fetch); exit code."""
    files = status.get("files") if isinstance(status.get("files"), dict) else None
    if not status.get("keep"):
        raise FetchError(f"job {job_id} named no files to keep", error_code="job.no_files")
    if status.get("state") != "finished":
        raise FetchError(f"job {job_id} is {status.get('state')}; fetch its files once it ended",
                         fix=f"`mulebox wait {job_id}`, then fetch")
    if not files or not files.get("packed"):
        _left_out(files, err)
        raise FetchError(f"job {job_id} kept no files", error_code="job.no_files")
    target = target.resolve()
    parent = target.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise FetchError(f"cannot make {parent}: {exc.strerror}",
                         fix="pass -o a folder you can write to") from None
    roots = Roots((parent,))
    with tempfile.TemporaryDirectory(prefix=f".{target.name}.", dir=parent) as scratch:
        pack = Path(scratch) / "files.tar.gz"
        remote.download_files(job_id, pack)
        unpacked = extract_tar(pack, Path(scratch) / "files", roots)
        if target.exists() or target.is_symlink():
            remove_tree(target, roots)
        os.replace(unpacked, target)
    ensure_dir(target, roots)
    report.status(err, f"{keep_files.summary(files)}, in {target}")
    _left_out(files, err)
    return 0


def kept_lines(job_id: str, result: dict[str, Any]) -> list[str]:
    """What a finished job kept and how to bring it here, for its end and its summary."""
    files = result.get("files") if isinstance(result.get("files"), dict) else None
    said = keep_files.summary(files)
    if not said:
        return []
    if not files.get("packed"):
        return [f"{said}; none to fetch (`mulebox logs {job_id}` says why)"]
    return [f"{said}: mulebox fetch {job_id}"]


def _left_out(files: dict[str, Any] | None, err: TextIO) -> None:
    if not files:
        return
    for line in files.get("left_out") or []:
        report.status(err, f"not kept: {line}")
    more = int(files.get("left_out_count") or 0) - len(files.get("left_out") or [])
    if more > 0:
        report.status(err, f"not kept: {more} more")
