"""What a person or agent has to hear about a job: questions, and results from while away.

Pure text from `status_ok`, `queue_ok` and `submit_ok` bodies, except `warn_here`, which asks
the coordinator on behalf of a command that does not otherwise see the queue. All of it goes to
stderr, so `--json` on stdout stays clean. A coordinator too old for any of this sends none of
these keys and nothing is printed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TextIO

from mulebox.client import json_end, report, stuck_lines
from mulebox.client.remote import Remote, request
from mulebox.client.report import format_duration
from mulebox.common import units
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
        parts.append(f"machine network {units.rate_kib(net)}")
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
        words += f": {units.size(done)} of {units.size(total)} ({done / total:.0%})"
    elif done is not None:
        words += f": {units.size(done)} so far"
    elif total:
        words += f" ({units.size(total)})"
    rate, age = number(download.get("rate_bytes_s")), number(download.get("as_of_s"))
    if rate is not None:
        words += f" at {units.rate(rate)}"
    if age is not None and age >= 30:
        words += f", as printed {format_duration(age)} ago"
    net = number(download.get("net_bytes_s"))
    if net is not None:
        whose = "its own" if download.get("net_scope") == "job" else "the machine's"
        words += f", network {units.rate(net)} ({whose})"
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
    for name in ("stuck", "moving"):
        seen = body.get(name)
        if isinstance(seen, dict):
            line = (stuck_lines.stuck_line(job_id, seen, WARNING) if name == "stuck"
                    else stuck_lines.moving_line(job_id, seen))
            return (name, seen.get("number")), line
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
    looks = stuck_lines.status_line(job_id, body.get("looks"))
    if looks:
        lines.append(looks)
    if isinstance(view, dict):
        lines.append(f"  question: is everything OK? It {stops_in(view)}. "
                     f"Yes: mulebox ok {job_id}. No: mulebox cancel {job_id}")
    return lines


def tell(body: dict[str, Any], err: TextIO) -> None:
    """Questions waiting for an answer and results from while away, from a reply's body."""
    for kind, item, text in notices(body):
        json_end.noticed({"kind": kind, "text": text, **item})
        report.status(err, text)


def notices(body: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    """Each notice in a reply's body: its kind, its data as the coordinator gave it, its line."""
    found = [("question", job, question_line(str(job.get("job_id")), job.get("question") or {}, job))
             for job in _dicts(body.get("questions"))]
    found += [("finished_away", job, away_line(job)) for job in _dicts(body.get("finished_away"))]
    found += [("low_disk", low, WARNING + disk.warning(
        str(low.get("worker")), int(low.get("free") or 0), _total(low.get("total"))))
        for low in _dicts(body.get("low_disks"))]
    found += [("heavy_node", heavy, heavy_line(heavy)) for heavy in _dicts(body.get("heavy_nodes"))]
    found += [("space_answer", answer, answer_line(answer))
              for answer in _dicts(body.get("space_answers"))]
    return found


def _total(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def heavy_line(heavy: dict[str, Any]) -> str:
    """A node where mulebox holds more than its warning size, 80% of the space it may use: for
    the agent to tell its user, who decides whether to give it more."""
    node, held = str(heavy.get("worker")), units.size(int(heavy.get("held") or 0))
    most = heavy.get("max")
    if not isinstance(most, int):  # a coordinator older than 1.30, or a node with no limit
        return (f"notice for the user: mulebox holds {held} on {node}, over the "
                f"{units.size(int(heavy.get('warn') or 0))} it warns at. Tell the user; "
                "`mulebox storage` shows what it holds and what goes when")
    start = (f"notice for the user: mulebox holds {held} on {node} of the {units.size(most)} it "
             "may use there; past that it removes older branch folders on its own. ")
    asked, declined = heavy.get("asked"), heavy.get("declined")
    if isinstance(asked, dict):
        return start + (f"You asked for {asked.get('value')}; it waits for the owner's answer on "
                        "the dashboard. Keep working; do not ask again")
    if isinstance(declined, dict):
        note = f" with the note: {declined['note']}" if declined.get("note") else ""
        return start + (f"The owner declined {declined.get('value')}{note}. Do not ask again; "
                        "tell the user if a job cannot run for lack of space")
    return start + ("Tell the user and ask whether to give it more; only with their yes: "
                    f"`mulebox storage ask --node {node} --size <size> --reason \"<why>\"`, which "
                    "they answer on the dashboard. `mulebox storage` shows what it holds and what "
                    "goes when")


def answer_line(ask: dict[str, Any]) -> str:
    """The owner's answer to this project's request for more space, told once."""
    node, answer = ask.get("node"), ask.get("answer") or {}
    if ask.get("state") == "declined":
        note = f", with the note: {answer['note']}" if answer.get("note") else ""
        return (f"the owner declined more space on {node} ({ask.get('value')} asked){note}. "
                "Do not ask again; tell the user if a job cannot run for lack of space")
    if ask.get("state") == "applied":
        return (f"more space on {node}: mulebox may use {answer.get('value')} there, applied "
                "without asking as the owner allows agents to; it is recorded")
    other = "" if answer.get("value") == ask.get("value") else f", not the {ask.get('value')} asked"
    return f"the owner approved more space on {node}: mulebox may use {answer.get('value')}{other}"


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
