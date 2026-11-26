"""A job's kept files, after its cleanup and before its result (docs/design.md, Files back).

Split from agent.py: `Agent` provides `link`, `paths`, `node`, `_online`. Finding and packing
the files (files_out.py) and sending the pack run beside the loop (background.py), as a pack can
be 200 MB: `packing`, then `packed`, then `sending`. A lost link sends the pack again on a later
step; a refusal from the coordinator does not, and the job's log says why. The result waits
until the files are done with, and carries what was kept (`files`).
"""

from __future__ import annotations

from typing import Any

from mulebox.common import units
from mulebox.common.log import get_logger
from mulebox.common.protocol import MessageType
from mulebox.common.safepath import remove_tree
from mulebox.common.status import COMMAND
from mulebox.worker import background, files_out
from mulebox.worker.job import ActiveJob
from mulebox.worker.link import LinkError

LOG = get_logger("worker.files")
PACKING, PACKED, SENDING = "packing", "packed", "sending"


class KeepingFiles:
    def _files_done(self, job: ActiveJob, now: float) -> bool:
        """Has the job's kept files' work ended, so its result can go?"""
        if job.files_report is not None:
            return True
        if not job.keep_files or job.tree is None or not job.steps.reached(COMMAND):
            return True  # nothing named, or the command never started
        task = job.files_task
        if task is not None:
            if not task.done:
                return False
            job.files_task = None
            if job.files_stage == PACKING:
                if task.error is not None or job.files_pack is None:
                    job.tailer.note(f"mulebox: the files to keep could not be packed: "
                                    f"{task.error}\n")
                    return self._files_end(job, packed=False)
                job.files_stage = PACKED
            elif isinstance(task.error, LinkError):
                LOG.warning("sending the files of %s failed (retrying): %s", job.job_id, task.error)
                job.files_stage = PACKED
            else:
                problem = str(task.error) if task.error is not None else job.files_refused
                if problem:
                    job.tailer.note(f"mulebox: the kept files did not reach the coordinator: "
                                    f"{problem}\n")
                return self._files_end(job, packed=not problem)
        if job.files_stage is None:
            job.files_stage = PACKING
            job.files_task = background.start_thread(lambda: self._pack_files(job))
            return False
        if not job.files_gathered.files:
            return self._files_end(job, packed=False)
        if self._online(now):
            job.files_stage = SENDING
            job.files_task = background.start_thread(lambda: self._send_files(job))
        return False

    def _pack_files(self, job: ActiveJob) -> None:
        gathered = files_out.gather(job.tree, job.keep_files,
                                    self.node.storage.keep_files_bytes())
        job.files_gathered = gathered
        if gathered.files:
            job.files_pack = files_out.pack(job.tree, gathered, self.paths.staging,
                                            self.paths.roots, job.job_id)
        else:
            job.files_pack = (None, "")

    def _send_files(self, job: ActiveJob) -> None:
        path, sha = job.files_pack
        reply = self.link.upload_files(job.job_id, path, sha)  # LinkError: tried again
        job.files_refused = (str(reply.body.get("message") or "refused")
                             if reply.type is MessageType.ERROR else None)

    def _files_end(self, job: ActiveJob, packed: bool) -> bool:
        gathered = job.files_gathered or files_out.Gathered()
        job.files_report = gathered.report(packed)
        if packed:
            job.tailer.note(f"mulebox: kept {len(gathered.files)} file(s), "
                            f"{units.size(gathered.size)}; bring them here with "
                            f"`mulebox fetch {job.job_id}`\n")
        for line in gathered.left_out[:10]:
            job.tailer.note(f"mulebox: not kept: {line}\n")
        if gathered.left_out_count > 10:
            job.tailer.note(f"mulebox: not kept: {gathered.left_out_count - 10} more\n")
        path = job.files_pack[0] if job.files_pack else None
        if path is not None:
            try:
                remove_tree(path, self.paths.roots)
            except OSError as exc:
                LOG.warning("could not remove the files pack of %s: %s", job.job_id, exc)
        return True

    def _files_result(self, job: ActiveJob) -> dict[str, Any]:
        return {"files": job.files_report} if job.files_report is not None else {}
