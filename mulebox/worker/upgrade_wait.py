"""The machine's side of an upgrade that waits its turn (coordinator/upgrades.py, M16.5).

    mulebox upgrade-queue --bundle DIR [--behind] [--client NAME]
    mulebox upgrade-wait <job-id> --bundle DIR
    mulebox upgrade-report <job-id> --log FILE (--passed | --failed)

`mulebox setup <machine> --queued` unpacks the new version into ~/.mulebox/tmp and runs
`upgrade-queue`, which moves it into `<staging>/upgrades/`, puts the upgrade in line and
starts the waiter apart (services `detach`: a systemd unit of its own, or a session of its own on
macOS), so it outlives the ssh session and the service
restarts the install makes. The waiter asks for its turn every few seconds; on it, it runs the
bundle's install.sh. The installed `mulebox` (the new one, as the waiter's own code is now
replaced) reports the result with the installer's output, and the bundle goes through safepath.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from mulebox.common import safepath
from mulebox.common.config import DEFAULT_REMOTE_BIN, load_node_config
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import Message, MessageType
from mulebox.common.redact import Redactor, secret_values
from mulebox.coordinator.validate import check_job_id
from mulebox.worker.link import request
from mulebox.services.manager import for_platform
from mulebox.worker.paths import NodePaths

ASK_EVERY_S = 5.0
INSTALL_TIMEOUT_S = 1500.0
_PROGRAM = str(Path(DEFAULT_REMOTE_BIN.replace("~", str(Path.home()), 1)))


def register(sub: argparse._SubParsersAction) -> None:
    queue = sub.add_parser("upgrade-queue", help="put an upgrade of this machine in line")
    queue.add_argument("--bundle", required=True, help="the unpacked new version")
    queue.add_argument("--behind", action="store_true",
                       help="behind the jobs already waiting, not next")
    queue.add_argument("--client", default="upgrade", help="who sent it, for the queue")
    queue.set_defaults(func=_queue)
    wait = sub.add_parser("upgrade-wait", help="wait for an upgrade's turn and install it")
    wait.add_argument("job_id")
    wait.add_argument("--bundle", required=True)
    wait.set_defaults(func=_wait)
    report = sub.add_parser("upgrade-report", help="report how an upgrade went")
    report.add_argument("job_id")
    report.add_argument("--log", required=True)
    report.add_argument("--passed", action="store_true")
    report.add_argument("--failed", action="store_true")
    report.set_defaults(func=_report)


def _open() -> tuple[Any, Any, NodePaths]:
    from mulebox.worker.commands import open_link

    node = load_node_config(None)
    paths = NodePaths.from_config(node.roots)
    return node, open_link(node, paths), paths


def _call(link: Any, **body: Any) -> dict[str, Any]:
    reply: Message = link.call(request(MessageType.UPGRADE, **body))
    if reply.type == MessageType.ERROR:
        raise MuleboxError(reply.body.get("message", "the coordinator refused"))
    return reply.body


def _wheel(bundle: Path) -> Path:
    found = sorted(bundle.glob("mulebox-*.whl"))
    if not found or not (bundle / "install.sh").is_file():
        raise MuleboxError(f"{bundle} holds no mulebox wheel and install.sh")
    return found[-1]


def _version(wheel: Path) -> str:
    return wheel.name.split("-")[1]


def _queue(args: argparse.Namespace) -> int:
    try:
        node, link, paths = _open()
        source = Path(args.bundle).resolve()
        version = _version(_wheel(source))
        home = safepath.ensure_dir(paths.staging / "upgrades", paths.roots)
        bundle = home / source.name
        shutil.move(str(source), str(bundle))
        made = _call(link, action="queue", worker=node.name, version=version,
                     first=not args.behind, client=args.client)
        try:
            for_platform().detach(f"mulebox-upgrade-{made['job_id'].lower()}", [
                _PROGRAM, "upgrade-wait", made["job_id"], "--bundle", str(bundle)])
        except MuleboxError as exc:
            link.call(request(MessageType.CANCEL, job_id=made["job_id"]))
            safepath.remove_tree(bundle, paths.roots)
            raise MuleboxError(f"could not start the waiter: {exc}") from exc
    except (MuleboxError, OSError) as exc:
        print(f"mulebox: {exc}", file=sys.stderr)
        return 2
    print(f"{made['job_id']} {version} {made.get('position') or ''}".strip())
    return 0


def _wait(args: argparse.Namespace) -> int:
    job_id = check_job_id(args.job_id)
    _, link, paths = _open()
    bundle = Path(args.bundle)
    while True:
        try:
            turn = _call(link, action="turn", job_id=job_id)
        except MuleboxError as exc:
            print(f"mulebox: asking for the turn failed, trying again: {exc}", file=sys.stderr)
            time.sleep(ASK_EVERY_S)
            continue
        if turn.get("outcome"):  # cancelled, or let go
            safepath.remove_tree(bundle, paths.roots)
            return 0
        if turn.get("go"):
            break
        time.sleep(ASK_EVERY_S)
    log = bundle / "install.log"  # goes with the bundle
    passed = _install(bundle, log)
    # The installed program reports: this process's own code was just replaced.
    subprocess.run([_PROGRAM, "upgrade-report", job_id, "--log", str(log),
                    "--passed" if passed else "--failed"], check=False)
    safepath.remove_tree(bundle, paths.roots)
    return 0 if passed else 1


def _install(bundle: Path, log: Path) -> bool:
    with log.open("wb") as out:
        try:
            done = subprocess.run(["bash", str(bundle / "install.sh"), str(_wheel(bundle))],
                                  stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  timeout=INSTALL_TIMEOUT_S, check=False)
        except (subprocess.TimeoutExpired, MuleboxError, OSError) as exc:
            out.write(f"\nmulebox: the install stopped: {exc}\n".encode())
            return False
    return done.returncode == 0


def _report(args: argparse.Namespace) -> int:
    node, link, _ = _open()
    log = Path(args.log)
    text = log.read_text(errors="replace") if log.is_file() else ""
    _call(link, action="done", job_id=check_job_id(args.job_id), passed=args.passed and not args.failed,
          log=Redactor(secret_values(node.job_env)).redact(text))
    return 0
