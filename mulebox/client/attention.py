"""What a person or agent has to hear about a job: questions, and results from while away.

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
from mulebox.client.report import format_duration, format_size
from mulebox.common.config import (
    ConfigError,
    find_project_config,
    load_client_config,
    load_project_config,
)
from mulebox.common.errors import MuleboxError
from mulebox.common.network_errors import LOST
from mulebox.common.protocol import MessageType
from mulebox.common import disk, status
from mulebox.common.status import FETCHING, number

WARNING = "warning: "
QUEUE_NOTHING_FINISHED = 0


def _name(job: dict[str, Any]) -> str:
    known = [str(job[key]) for key in ("project", "job") if job.get(key)]
    return f" ({' '.join(known)})" if known else ""


def stops_in(view: dict[str, Any]) -> str:
    """When a job stops if it stays stuck. A working job does not: this time keeps moving."""
    return f"stops in {format_duration(number(view.get('left_s')))} if it stays stuck"


def question_line(job_id: str, view: dict[str, Any], job: dict[str, Any] | None = None) -> str:
    """The reminder of a question not answered yet; it names both answers."""
    return (f"{WARNING}job {job_id}{_name(job or {})} has run a long time: is everything OK? "
            f"While it works it goes on; it {stops_in(view)}. Yes: mulebox ok {job_id}. "
            f"No: mulebox cancel {job_id}")


def result_words(job: dict[str, Any]) -> str:
    code = job.get("exit_code")
    words = str(status.outcome_of(job)) + (f", exit {code}" if code is not None else "")
    commit = job.get("base_commit")
    return f"{words}, on commit {str(commit)[:10]}" if commit else words


def away_line(job: dict[str, Any]) -> str:
    """A result nobody received: the agent need not run the job again."""
    job_id = job.get("job_id")
    return (f"job {job_id}{_name(job)} finished while you were away: {result_words(job)}. "
            f"No need to retest; its log: mulebox logs {job_id}")


def already_line(job: dict[str, Any]) -> str:
    """`check` found the same job on the same files."""
    job_id = job.get("job_id")
    if job.get("state") != "finished":
        return f"this exact job is already {job.get('state')} as {job_id}: following that one"
    return (f"already tested: job {job_id}{_name(job)} ran on exactly these files: "
            f"{result_words(job)}. Not run again; to force a run: --again. "
            f"Its log: mulebox logs {job_id}")


def activity_text(activity: dict[str, Any]) -> str:
    """The readings there are; the worker leaves out what it could not measure."""
    parts = []
    if activity.get("stage"):
        parts.append(f"stage {activity['stage']}")
    quiet = number(activity.get("output_idle_s"))
    if quiet is not None:
        parts.append(f"last output {format_duration(quiet)} ago")
    job_cpu = number(activity.get("job_cpu_pct"))
    if job_cpu is not None:
        parts.append(f"job CPU {job_cpu:.0f}% of a core")
    cpu, net = number(activity.get("cpu_pct")), number(activity.get("net_kib_s"))
    if cpu is not None:
        parts.append(f"machine CPU {cpu:.0f}% of a core")
    if net is not None:
        parts.append(f"machine network {net:.1f} KiB/s")
    if activity.get("last_line"):
        parts.append(f"last line: {activity['last_line']}")
    if isinstance(activity.get("download"), dict):
        parts.append(download_text(activity["download"]))
    return ", ".join(parts) or "no readings from the machine"


def download_text(download: dict[str, Any]) -> str:
    """What a job is downloading (common/download_watch.py), as far as the readings go."""
    name = download.get("name") or download.get("what")
    done, total = number(download.get("done_bytes")), number(download.get("total_bytes"))
    words = f"downloading {name}" if name != "network" else "downloading, by its own traffic"
    if done is not None and total:
        words += f": {format_size(int(done))} of {format_size(int(total))} ({done / total:.0%})"
    elif done is not None:
        words += f": {format_size(int(done))} so far"
    elif total:
        words += f" ({format_size(int(total))})"
    rate, age = number(download.get("rate_bytes_s")), number(download.get("as_of_s"))
    if rate is not None:
        words += f" at {format_size(int(rate))}/s"
    if age is not None and age >= 30:
        words += f", as printed {format_duration(age)} ago"
    net = number(download.get("net_bytes_s"))
    if net is not None:
        whose = "its own" if download.get("net_scope") == "job" else "the machine's"
        words += f", network {format_size(int(net))}/s ({whose})"
    if download.get("waiting_on_network"):
        words += ", waiting on the network"
    quiet = number(download.get("quiet_s"))
    if download.get("stalled") and quiet is not None:
        words += f", stalled: no byte for {format_duration(quiet)}"
    return words


def check_in_line(job_id: str, check_in: dict[str, Any]) -> str:
    took = format_duration(number(check_in.get("elapsed_s")))
    return (f"{WARNING}check-in: job {job_id} has run {took}; {activity_text(check_in)}. "
            f"Is everything OK? Yes: mulebox ok {job_id}. No: mulebox cancel {job_id}")


def notice(job_id: str, body: dict[str, Any]) -> tuple[Any, str] | None:
    """(a key that is the same on a reconnect, the line) for a body that carries a notice."""
    check_in = body.get("check_in")
    if isinstance(check_in, dict):
        return ("check_in", check_in.get("number")), check_in_line(job_id, check_in)
    return None


def network_trouble(activity: dict[str, Any]) -> bool:
    """Whether a job that is fetching things printed a lost connection last. Not in `command`:
    a project's own tests can print that on purpose."""
    line = activity.get("last_line")
    return activity.get("stage") in FETCHING and bool(line and LOST.search(str(line)))


def status_lines(body: dict[str, Any]) -> list[str]:
    """`mulebox status`: what the job is doing and what it is waiting to hear."""
    job_id, lines = str(body.get("job_id")), []
    activity, view = body.get("activity"), body.get("question")
    if isinstance(activity, dict):
        took = format_duration(number(activity.get("elapsed_s")))
        lines.append(f"  activity: running {took}, {activity_text(activity)}")
        if network_trouble(activity):
            lines.append("  warning: its last line reads as a lost connection; downloads may be "
                         "retrying, and this is the machine's network, not the project")
    if isinstance(view, dict):
        lines.append(f"  question: is everything OK? It {stops_in(view)}. "
                     f"Yes: mulebox ok {job_id}. No: mulebox cancel {job_id}")
    return lines


def tell(body: dict[str, Any], err: TextIO) -> None:
    """Questions waiting for an answer and results from while away, from a reply's body."""
    for job in _dicts(body.get("questions")):
        report.status(err, question_line(str(job.get("job_id")), job.get("question") or {}, job))
    for job in _dicts(body.get("finished_away")):
        report.status(err, away_line(job))
    for low in _dicts(body.get("low_disks")):
        report.status(err, WARNING + disk.warning(str(low.get("worker")), int(low.get("free") or 0)))


def _dicts(items: Any) -> list[dict[str, Any]]:
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def tell_here(err: TextIO, folder: Path | None = None) -> None:
    """Tell this project's news. Only a remark on another command's way out: nothing that goes
    wrong here may change what that command returned."""
    try:
        project = load_project_config(find_project_config(folder or Path.cwd())).project
        remote = Remote(load_client_config())
        reply = remote.call(request(MessageType.QUEUE, limit=QUEUE_NOTHING_FINISHED,
                                    news_for=project))
    except (ConfigError, MuleboxError, OSError):
        return
    tell(reply.body, err)
