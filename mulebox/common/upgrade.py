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


KINDS = ("checkout", "pipx", "uv", "other")
_BY_KIND = {"checkout": CHECKOUT, "pipx": PIPX, "uv": UV}


def kind(prefix: str | None = None) -> str:
    """How the running mulebox was installed: one of KINDS. A dev machine reports it with
    every request (client/dev_machine.py), so the node's dashboard names the right upgrade."""
    if prefix is None and version.in_checkout():
        return "checkout"
    where = Path(prefix or sys.prefix).as_posix()
    if "/pipx/venvs/" in where:
        return "pipx"
    if "/uv/tools/" in where:
        return "uv"
    return "other"


def for_kind(name: str | None) -> str:
    """The upgrade for an install of that kind; both PyPI ways when it is not known."""
    return _BY_KIND.get(name or "", EITHER)


def command(prefix: str | None = None) -> str:
    """The upgrade for the mulebox that is running, from where it was installed."""
    return for_kind(kind(prefix))
