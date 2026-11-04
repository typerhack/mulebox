"""What a person or agent has to decide about a job: check-ins and unattended warnings.

Pure text from `status_ok`, `queue_ok` and `submit_ok` bodies, except `warn_here`, which asks
the coordinator on behalf of a command that does not otherwise see the queue. All of it goes to
stderr, so `--json` on stdout stays clean. A coordinator too old for any of this sends none of
these keys and nothing is printed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TextIO

from mulebox.client import report
from mulebox.client.remote import Remote, request
from mulebox.client.report import format_duration
from mulebox.common.config import (
    ConfigError,
    find_project_config,
    load_client_config,
    load_project_config,
)
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import MessageType
from mulebox.common.status import number

WARNING = "warning: "
QUEUE_NOTHING_FINISHED = 0


def _name(job: dict[str, Any]) -> str:
    known = [str(job[key]) for key in ("project", "job") if job.get(key)]
    return f" ({' '.join(known)})" if known else ""


def stops_in(view: dict[str, Any]) -> str:
    return f"stops in {format_duration(number(view.get('left_s')))}: {view.get('reason')}"


def unattended_line(job_id: str, view: dict[str, Any], job: dict[str, Any] | None = None) -> str:
    """The warning for a job nobody is watching; it names both ways out."""
    if view.get("taken_back"):
        return (f"{WARNING}job {job_id} was unattended and would have stopped in "
                f"{format_duration(number(view.get('left_s')))}; it is being watched again")
    return (f"{WARNING}job {job_id}{_name(job or {})} is unattended, nobody is watching it, and it "
            f"{stops_in(view)}. Take it back: mulebox wait {job_id}. "
            f"Stop it: mulebox cancel {job_id}")


def activity_text(activity: dict[str, Any]) -> str:
    """The readings there are; the worker leaves out what it could not measure."""
    parts = []
    if activity.get("stage"):
        parts.append(f"stage {activity['stage']}")
    quiet = number(activity.get("output_idle_s"))
    if quiet is not None:
        parts.append(f"last output {format_duration(quiet)} ago")
    cpu, net = number(activity.get("cpu_pct")), number(activity.get("net_kib_s"))
    if cpu is not None:
        parts.append(f"machine CPU {cpu:.0f}% of a core")
    if net is not None:
        parts.append(f"machine network {net:.1f} KiB/s")
    return ", ".join(parts) or "no readings from the machine"


def check_in_line(job_id: str, check_in: dict[str, Any]) -> str:
    took = format_duration(number(check_in.get("elapsed_s")))
    return (f"{WARNING}check-in: job {job_id} has run {took}; {activity_text(check_in)}. "
            f"Decide whether it is stuck; to stop it: mulebox cancel {job_id}")


def notice(job_id: str, body: dict[str, Any]) -> tuple[Any, str] | None:
    """(a key that is the same on a reconnect, the line) for a body that carries a notice."""
    check_in, view = body.get("check_in"), body.get("unattended")
    if isinstance(check_in, dict):
        return ("check_in", check_in.get("number")), check_in_line(job_id, check_in)
    if isinstance(view, dict):
        return ("unattended", view.get("since")), unattended_line(job_id, view)
    return None


def status_lines(body: dict[str, Any]) -> list[str]:
    """`mulebox status`: what the job is doing and who is watching it."""
    job_id, lines = str(body.get("job_id")), []
    activity, view = body.get("activity"), body.get("unattended")
    if isinstance(activity, dict):
        took = format_duration(number(activity.get("elapsed_s")))
        lines.append(f"  activity: running {took}, {activity_text(activity)}")
    if body.get("attended") is True:
        lines.append("  watched: yes")
    elif isinstance(view, dict):
        lines.append(f"  watched: no, unattended; it {stops_in(view)}. "
                     f"Take it back: mulebox wait {job_id}")
    return lines


def warn(jobs: Any, err: TextIO) -> None:
    """One warning for each job that carries an `unattended` view."""
    for job in jobs if isinstance(jobs, list) else ():
        if isinstance(job, dict) and isinstance(job.get("unattended"), dict):
            report.status(err, unattended_line(str(job.get("job_id")), job["unattended"], job))


def warn_here(err: TextIO, folder: Path | None = None) -> None:
    """Warn about this project's unattended jobs. Only a remark on another command's way out:
    nothing that goes wrong here may change what that command returned."""
    try:
        project = load_project_config(find_project_config(folder or Path.cwd())).project
        remote = Remote(load_client_config())
        reply = remote.call(request(MessageType.QUEUE, limit=QUEUE_NOTHING_FINISHED))
    except (ConfigError, MuleboxError, OSError):
        return
    jobs = reply.body.get("jobs")
    warn([j for j in jobs if isinstance(j, dict) and j.get("project") == project]
         if isinstance(jobs, list) else [], err)
