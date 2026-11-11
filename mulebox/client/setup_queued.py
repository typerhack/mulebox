"""`mulebox setup <machine> --queued [--behind]`: an upgrade that waits its turn (M16.5).

The new version goes to the machine at once and the dev machine is free again: on the machine it
is a row in the line (coordinator/upgrades.py, worker/upgrade_wait.py). By default it goes
next, so nothing new starts there and it installs as soon as the running jobs end; `--behind`
lets the jobs already waiting go first. It shows in `mulebox queue` and on the dashboard,
`mulebox status <id>` follows it, and `mulebox cancel <id>` takes it back while it waits.
"""

from __future__ import annotations

import shlex
import tempfile
import time
from pathlib import Path

from mulebox.client import setup, sshio
from mulebox.common import ssh
from mulebox.common.errors import MuleboxError

_TOO_OLD = "invalid choice: 'upgrade-queue'"


def run(target: str, say: setup.Say, behind: bool = False) -> str:
    """Put the upgrade in line on `target`; its job id."""
    say(f"checking the login to {target}")
    setup.check_login(target)
    folder = f".mulebox/tmp/upgrade-{time.strftime('%Y%m%d-%H%M%S')}"
    with tempfile.TemporaryDirectory(prefix="mulebox-setup-") as local:
        bundle, _ = setup._pack(Path(local))
        unpack = f'mkdir -p "$HOME/{folder}" && tar xzf - -C "$HOME/{folder}"'
        sent = sshio.run_with_file(target, ["sh", "-c", unpack], bundle,
                                   connect_timeout_s=setup.CONNECT_S)
    sshio.check_exit(target, ["tar"], sent.exit_code, sent.stderr)
    script = (f'exec "$HOME/{setup.PROGRAM}" upgrade-queue --bundle "$HOME/{folder}"'
              f'{" --behind" if behind else ""} --client {shlex.quote("setup")}')
    done = ssh.run_remote(target, ["sh", "-c", script], timeout_s=setup.LOGIN_TIMEOUT_S,
                          connect_timeout_s=setup.CONNECT_S, check=False)
    out, err = done.stdout.decode(errors="replace"), done.stderr.decode(errors="replace")
    if done.exit_code != 0:
        if _TOO_OLD in err:
            raise setup.SetupError(f"the mulebox on {target} is older than queued upgrades; "
                                   "upgrade it once with --when-idle")
        raise setup.SetupError(f"{target} did not take the upgrade: {err.strip()}")
    try:
        job_id, version, *place = out.split()
    except ValueError:
        raise MuleboxError(f"{target} answered {out!r}") from None
    where = f"#{place[0]} in line" if place else "in line"
    nothing = ("nothing new starts there until it is done" if not behind
               else "the jobs already waiting go first")
    say(f"upgrade to {version} is {where} on {target} as {job_id}; {nothing}")
    say(f"follow it: mulebox status {job_id}; take it back while it waits: mulebox cancel {job_id}")
    return job_id
