"""`mulebox setup <worker> --worker-of <coordinator>`: one more build machine for the queue.

Both machines must take `ssh <host> true` from here. The steps, each said as it runs:

1. The coordinator machine runs mulebox already (`mulebox setup <coordinator>` first).
2. On the worker, a key of its own, ~/.config/mulebox/coordinator_key, made once.
3. The coordinator lets that key in for `mulebox rpc` only (coordinator/worker_keys.py).
4. mulebox is installed on the worker; a new node.toml there is a worker of the coordinator,
   which it reaches at the address from `ssh -G <coordinator>`, or `--coordinator-address`.
5. What the worker offers, then: the coordinator lists it online, or setup says what to check.

Run again, it upgrades the worker; its node.toml, key and authorization are kept or replaced
the same way. A worker's running jobs stop it unless `--now`.
"""

from __future__ import annotations

import re
import subprocess
import time

from mulebox.client import setup
from mulebox.client.remote import request
from mulebox.client.setup import PROGRAM, SetupError, Say
from mulebox.common import ssh
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import MessageType

KEY = ".config/mulebox/coordinator_key"
ONLINE_WAIT_S = 45.0
_MAKE_KEY = (f'k="$HOME/{KEY}"; mkdir -p "$(dirname "$k")" && '
             '{ [ -f "$k" ] || ssh-keygen -q -t ed25519 -N "" -C mulebox-worker -f "$k"; } && '
             'cat "$k.pub" && printf "%s\\n" "$HOME"')
_NAME = ('n="$(hostname -s 2>/dev/null || hostname)"; '
         f'"$HOME/.mulebox/venv/bin/python" -c "from mulebox.common.config import '
         'load_node_config; print(load_node_config().name)" 2>/dev/null || printf "%s\\n" "$n"')


def coordinator_address(coordinator: str) -> str:
    """`ssh -G` of the laptop's own alias -> ssh://user@host:port, which the worker can use."""
    done = subprocess.run(["ssh", "-G", coordinator], capture_output=True, text=True, check=False)
    seen = dict(line.split(" ", 1) for line in done.stdout.splitlines() if " " in line)
    if done.returncode != 0 or "hostname" not in seen:
        raise SetupError(f"cannot work out the address of {coordinator}; "
                         "give it with --coordinator-address alice@192.168.1.50")
    user = f"{seen['user']}@" if seen.get("user") else ""
    return f"ssh://{user}{seen['hostname']}:{seen.get('port', '22')}"


def marker_name(target: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", target).strip("-.") or "worker"


def _run(target: str, script: str, stdin: bytes | None = None) -> str:
    return ssh.run_remote(target, ["sh", "-c", script], stdin=stdin,
                          timeout_s=setup.LOGIN_TIMEOUT_S,
                          connect_timeout_s=setup.CONNECT_S).stdout.decode()


def make_key(worker: str) -> tuple[str, str]:
    """The worker's public key line and the absolute path of its private key."""
    lines = _run(worker, _MAKE_KEY).splitlines()
    if len(lines) < 2 or not lines[-1].startswith("/"):
        raise SetupError(f"could not make a key on {worker} (is ssh-keygen there?)")
    return lines[0], f"{lines[-1].rstrip('/')}/{KEY}"


def authorize(coordinator: str, name: str, public_key: str) -> None:
    try:
        ssh.run_remote(coordinator, [PROGRAM, "authorize-worker", name],
                       stdin=public_key.encode() + b"\n", timeout_s=setup.LOGIN_TIMEOUT_S,
                       connect_timeout_s=setup.CONNECT_S)
    except ssh.RemoteError as exc:
        raise SetupError(f"{coordinator} did not take the worker's key: {exc}. Is mulebox "
                         f"there, and new enough? `mulebox setup {coordinator}` first") from exc


def worker_jobs(coordinator: str, name: str) -> list[str]:
    try:
        rows = setup.remote_for(coordinator).call(request(MessageType.QUEUE)).body["jobs"]
    except (MuleboxError, OSError, KeyError):
        return []
    return [row["job_id"] for row in rows if row.get("worker") == name
            and row.get("state") in ("starting", "running", "cleaning")]


def wait_online(coordinator: str, name: str) -> dict | None:
    deadline = time.monotonic() + ONLINE_WAIT_S
    while True:
        try:
            reply = setup.remote_for(coordinator).call(request(MessageType.MACHINES))
            row = next((w for w in reply.body.get("workers", []) if w["worker"] == name), None)
        except (MuleboxError, OSError):
            row = None
        if (row and row.get("online")) or time.monotonic() > deadline:
            return row if row and row.get("online") else None
        time.sleep(3.0)


def run(worker: str, coordinator: str, say: Say, address: str | None = None,
        now: bool = False) -> None:
    for target in (coordinator, worker):
        say(f"checking the login to {target}")
        setup.check_login(target)
    address = address or coordinator_address(coordinator)
    name = _run(worker, _NAME).strip().splitlines()[-1]
    if not now and (jobs := worker_jobs(coordinator, name)):
        raise SetupError(f"{len(jobs)} job(s) are running on {worker}, and an upgrade would "
                         "stop them. Wait for them, or add --now.")
    try:
        say(f"making a key on {worker} for {coordinator}")
        public_key, key_path = make_key(worker)
        say(f"letting that key reach {coordinator}, for mulebox requests only")
        authorize(coordinator, marker_name(name), public_key)
        say(f"installing mulebox on {worker}, a worker of {address}")
        setup.install(worker, {"MULEBOX_COORDINATOR": address, "MULEBOX_COORDINATOR_KEY": key_path})
        setup.find_offers(worker, say)
        name = _run(worker, _NAME).strip().splitlines()[-1]
    except (MuleboxError, OSError, ValueError, subprocess.SubprocessError) as exc:
        if isinstance(exc, SetupError):
            raise
        raise SetupError(f"setup stopped: {exc}. Fix that and run it again") from exc
    say(f"waiting for {coordinator} to see {name}")
    row = wait_online(coordinator, name)
    if row is None:
        raise SetupError(
            f"{coordinator} does not see {name}. On {worker}, `journalctl --user -u "
            f"mulebox-worker` says why; often {address} cannot be reached from there "
            "(give another with --coordinator-address)")
    say(f"{name} is in the queue: {row.get('slots')} slot(s), offers "
        f"{', '.join(row.get('capabilities') or []) or 'plain jobs'}")
