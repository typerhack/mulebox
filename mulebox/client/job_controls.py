"""`mulebox pause|resume|first|boost|normal <job-id>`: steer one job (coordinator/job_control.py).

    mulebox pause <job-id>     a waiting job keeps its place and does not start; a running one
                               is frozen on its machine, containers too, until resumed
    mulebox resume <job-id>    undo a pause
    mulebox first <job-id>     a waiting job goes before every other waiting job
    mulebox boost <job-id>     the job gets the machine's CPU and disk first, and its machine
                               takes no new job until it ends
    mulebox normal <job-id>    back to its own place in line, without the boost

Pausing a whole machine is `mulebox machine pause <name>` (machine_commands.py).
"""

from __future__ import annotations

import argparse
import sys

from mulebox.client.commands import connect, guarded
from mulebox.client.remote import request
from mulebox.common.protocol import MessageType

HELP = {
    "pause": "pause a job: a waiting one does not start, a running one is frozen",
    "resume": "resume a paused job",
    "first": "run a waiting job before every other waiting job",
    "boost": "give a job the machine's CPU and disk first; the machine takes no new job",
    "normal": "put a job back in its own place in line, without the boost",
}
DONE = {
    "pause": "paused", "resume": "resumed", "first": "moved first in line",
    "boost": "boosted", "normal": "back to normal",
}


def register(sub: argparse._SubParsersAction) -> None:
    for action, text in HELP.items():
        parser = sub.add_parser(action, help=text)
        parser.add_argument("job_id")
        parser.set_defaults(func=guarded(_control, notices=True), action=action)


def line(job_id: str, action: str, body: dict) -> str:
    """What the command says it did, with what that means for this job now."""
    state = body.get("state", "unknown")
    if action == "pause" and state == "running":
        note = "frozen on its machine within seconds; `mulebox resume` goes on where it stopped"
    elif action == "pause":
        note = "it keeps its place and does not start"
    elif action == "boost" and state != "running":
        note = "first in line, and it gets its machine to itself once it starts"
    else:
        note = f"state {state}"
    return f"mulebox: job {job_id} {DONE[action]}: {note}"


def _control(args: argparse.Namespace) -> int:
    reply = connect().call(request(MessageType.JOB_CONTROL, job_id=args.job_id,
                                   action=args.action))
    print(line(args.job_id, args.action, reply.body), file=sys.stderr)
    return 0
