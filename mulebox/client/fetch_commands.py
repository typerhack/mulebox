"""`mulebox fetch <job>`: the files a job kept, into the project (client/fetch.py)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mulebox.client import fetch, json_end
from mulebox.client.commands import connect, guarded, project_here
from mulebox.client.remote import request
from mulebox.common.protocol import MessageType


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("fetch", help="bring the files a job kept (`keep:`, `--keep`) here")
    parser.add_argument("job_id")
    parser.add_argument("-o", "--output", type=Path, metavar="DIR",
                        help="put them in DIR/<job>/ rather than .mulebox/files/<job>/ in the project")
    json_end.add(parser)
    parser.set_defaults(func=guarded(_fetch, notices=True))


def _fetch(args: argparse.Namespace) -> int:
    remote = connect()
    status = remote.call(request(MessageType.STATUS, job_id=args.job_id)).body
    root = Path.cwd() if args.output is not None else project_here()[1]
    target = fetch.target_for(root, args.job_id, args.output)
    json_end.record(job_id=args.job_id, folder=str(target), files=status.get("files"))
    return fetch.fetch(remote, args.job_id, status, target, sys.stderr)
