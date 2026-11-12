"""The job-started hook inside an isolated runner's container, and the files it talks through.

It runs where the job will, before any step, so it holds nothing of the node: it writes the
job's GitHub values and a copy of its event file to the mounted `io` folder, and waits for the
node's answer there (place_bridge.py: the guard, then the build slot). Allowed: it exits 0 and
the job goes on. Refused, or no answer: it writes the reason to the job process's stderr, so
GitHub shows it, and kills that process (`Runner.Worker`), as a failed hook alone would let
`if: always()` steps run (guard.py). Even then the job never leaves its container.

The scripts are written into the place's `hooks` folder, mounted read-only, each time a
container starts, so an upgrade of mulebox reaches the next job.
"""

from __future__ import annotations

import os
from pathlib import Path

from mulebox.common.safepath import ensure_dir
from mulebox.runners import layout
from mulebox.worker.paths import NodePaths

HOOKS_MOUNT = "/mulebox-hooks"
IO_MOUNT = "/mulebox-io"
REQUEST = "request.json"
ANSWER = "answer.json"
EVENT = "event.json"
WAIT_S = 6 * 3600  # the node's own slot wait gives up before this (hooks.DEFAULT_TIMEOUT_MIN)

STARTED_SH = f"""#!/bin/sh
# Written by mulebox for an isolated runner: hand the job to the node and wait for its answer.
exec python3 {HOOKS_MOUNT}/started.py
"""

STARTED_PY = f'''"""mulebox, inside an isolated runner's container: ask the node whether this job may run."""
import json, os, shutil, signal, sys, time

IO = "{IO_MOUNT}"
env = {{k: v for k, v in os.environ.items() if k.startswith("GITHUB_") or k == "RUNNER_NAME"}}
try:
    shutil.copyfile(os.environ["GITHUB_EVENT_PATH"], os.path.join(IO, "{EVENT}"))
except (KeyError, OSError):
    pass
tmp = os.path.join(IO, "request.tmp")
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(env, fh)
os.replace(tmp, os.path.join(IO, "{REQUEST}"))
answer, deadline, said = None, time.monotonic() + {WAIT_S}, 0.0
while answer is None and time.monotonic() < deadline:
    try:
        with open(os.path.join(IO, "{ANSWER}"), encoding="utf-8") as fh:
            answer = json.load(fh)
    except (OSError, ValueError):
        if time.monotonic() - said > 60:
            print("mulebox: waiting for the node's answer", flush=True)
            said = time.monotonic()
        time.sleep(1)
if not isinstance(answer, dict):
    answer = {{"ok": False, "message": "mulebox: the node did not answer this job"}}
message = str(answer.get("message") or "")
if message:
    print(message, flush=True)
if answer.get("ok") is True:
    sys.exit(0)


def worker(pid):
    for _ in range(8):
        try:
            with open(f"/proc/{{pid}}/stat", encoding="utf-8") as fh:
                pid = int(fh.read().rsplit(")", 1)[1].split()[1])
            with open(f"/proc/{{pid}}/cmdline", "rb") as fh:
                args = fh.read().split(b"\\0")
        except (OSError, ValueError, IndexError):
            return None
        if any(os.path.basename(a.decode(errors="replace")) == "Runner.Worker" for a in args):
            return pid
    return None


pid = worker(os.getpid())
if pid:
    try:
        with open(f"/proc/{{pid}}/fd/2", "w", encoding="utf-8") as err:
            err.write(message + "\\n")
    except OSError:
        pass
    os.kill(pid, signal.SIGKILL)
sys.exit(1)
'''


def write_hooks(paths: NodePaths, folder: Path) -> Path:
    """Write both files into `<folder>/hooks`; return that folder (mounted read-only)."""
    hooks = ensure_dir(folder / "hooks", paths.roots)
    os.chmod(hooks, 0o755)  # the container's own user is not the node's: it reads, never writes
    layout.write_file(paths, hooks / "started.sh", STARTED_SH, 0o755)
    layout.write_file(paths, hooks / "started.py", STARTED_PY, 0o644)
    return hooks
