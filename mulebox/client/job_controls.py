"""`mulebox pause|resume|first|up|down|last|boost|normal <job-id>`: steer one job.

    mulebox pause <job-id>     a waiting job keeps its place and does not start; a running one
                               is frozen on its machine, containers too, until resumed
    mulebox resume <job-id>    undo a pause
    mulebox first <job-id>     a waiting job goes to the front of the line
    mulebox up <job-id>        one place ahead in line
    mulebox down <job-id>      one place back in line
    mulebox last <job-id>      to the end of the line
    mulebox boost <job-id>     the job gets the machine's CPU and disk first, and its machine
                               takes no new job until it ends
    mulebox normal <job-id>    end the boost; the job keeps its place in line

The rules are the coordinator's (coordinator/job_control.py). Pausing a whole machine is `mulebox machine pause <name>` (machine_commands.py).
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
    "first": "move a waiting job to the front of the line",
    "up": "move a waiting job one place ahead in line",
    "down": "move a waiting job one place back in line",
    "last": "move a waiting job to the end of the line",
    "boost": "give a job the machine's CPU and disk first; the machine takes no new job",
    "normal": "end a job's boost; it keeps its place in line",
}
DONE = {
    "pause": "paused", "resume": "resumed", "first": "moved to the front of the line",
    "up": "moved one place ahead", "down": "moved one place back", "last": "moved to the end of the line",
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
    elif body.get("position"):
        note = f"now #{body['position']} in line"
    else:
        note = f"state {state}"
    return f"mulebox: job {job_id} {DONE[action]}: {note}"


def _control(args: argparse.Namespace) -> int:
    reply = connect().call(request(MessageType.JOB_CONTROL, job_id=args.job_id,
                                   action=args.action))
    print(line(args.job_id, args.action, reply.body), file=sys.stderr)
    return 0
