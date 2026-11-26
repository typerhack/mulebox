"""An upgrade on trial (docs/design.md, Upgrades on trial, M23.7).

install.sh runs `mulebox service trial` with the new version once it has restarted the services.
For `TRIAL_S` seconds every service the node's roles run must keep running as the same run
(`Manager.instance`: a crash that systemd or launchd restarts counts as a stop), and a worker
must reach its coordinator once (worker/contact.py) after the services were restarted. The first
failure is the answer, said in one line; install.sh then goes back to the version before.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from mulebox.services.base import Manager, settled_state

TRIAL_S = 60.0
EVERY_S = 2.0


def run(manager: Manager, names: Sequence[str], since: float, version: str,
        contact: Callable[[], dict | None] | None, seconds: float = TRIAL_S,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time) -> str | None:
    """None when the services held; else why not."""
    start = clock()
    first: dict[str, str] = {}
    for name in names:
        settled_state(manager, name, sleep=sleep, clock=clock)
        if (now := manager.instance(name)) is None:
            return f"the {name} service is not running after the upgrade"
        first[name] = now
    reached = contact is None
    while True:
        for name in names:
            now = manager.instance(name)
            if now != first[name]:
                what = "stopped" if now is None else "restarted (it crashed, or was restarted)"
                return f"the {name} service {what} {clock() - start:.0f} s after the upgrade"
        reached = reached or _reached(contact(), since, version, wall)
        if clock() - start >= seconds:
            break
        sleep(EVERY_S)
    if not reached:
        return f"the worker did not reach its coordinator within {seconds:.0f} s of the upgrade"
    return None


def _reached(said: dict | None, since: float, version: str, wall: Callable[[], float]) -> bool:
    if not said:
        return False
    at = said.get("at")
    return (said.get("version") == version and isinstance(at, (int, float))
            and since - 1 <= at <= wall() + 60)
