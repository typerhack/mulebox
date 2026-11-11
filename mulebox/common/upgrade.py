"""How to upgrade mulebox on a dev machine, said the same way in every message.

mulebox is published on PyPI, so an upgrade fetches the newest release there: with pipx or uv,
whichever installed it. A checkout upgrades with git. A node is never upgraded this
way: `mulebox setup <host>` sends it the dev machine's own version.
"""

from __future__ import annotations

import sys
from pathlib import Path

from mulebox import version

PIPX = "`pipx upgrade mulebox`"
UV = "`uv tool upgrade mulebox`"
EITHER = f"{PIPX} (or {UV} if uv installed it)"
CHECKOUT = "`git pull` in the mulebox checkout"


def command(prefix: str | None = None) -> str:
    """The upgrade for the mulebox that is running, from where it was installed."""
    if prefix is None and version.in_checkout():
        return CHECKOUT
    where = Path(prefix or sys.prefix).as_posix()
    if "/pipx/venvs/" in where:
        return PIPX
    if "/uv/tools/" in where:
        return UV
    return EITHER
