"""What a dev machine says about itself with every request: its name, mulebox, skill and install.

The node keeps the newest word per dev machine (coordinator/clients.py) for the dashboard's
out-of-step strip. Said with every request, not only with a job, so an upgrade shows at once:
before, a dev machine that sent no job since its upgrade read as the old version for days.
Worked out once per process, as the skill state reads the skill copies from disk.
"""

from __future__ import annotations

import functools
import socket
from typing import Any

from mulebox.client import skill_install
from mulebox.common import upgrade
from mulebox.version import get_version

FIELD = "dev_machine"  # the request body field (interfaces-m1.md)


def name() -> str:
    return socket.gethostname() or "client"


@functools.cache
def said() -> dict[str, Any]:
    return {"client": name(), "version": get_version(), "skill": skill_install.state_here(),
            "install": upgrade.kind()}
