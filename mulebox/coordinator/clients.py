"""The dev machines that send jobs: the mulebox each last ran, and the state of its agent skill.

Every `submit` says it (`client_version`, `skill`, `client_install`), and since 1.43.0 every other
request too, in a `dev_machine` field (client/dev_machine.py): before, a dev machine upgraded with
no job sent since read as its old version. The newest word per client is kept, so the dashboard
can warn when a dev machine and the node are out of step (dashboard/notices.py) and name the
upgrade for how it was installed (`install`, common/upgrade.py KINDS). A client older than 0.83.0
says nothing and is simply not listed. `client` is the dev machine's host name, as on its jobs.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from mulebox.common import upgrade
from mulebox.common.log import get_logger
from mulebox.common.versions import parse
from mulebox.coordinator.errors import BadRequest

if TYPE_CHECKING:  # store imports migrate, which imports this module
    from mulebox.coordinator.store import Store

_log = get_logger(__name__)

SKILL_STATES = ("current", "out_of_date", "none")
RECENT_DAYS = 14  # a dev machine not seen for longer is left out: it may be gone
FIELD = "dev_machine"  # the field on requests other than submit (client/dev_machine.py)
REFRESH_S = 600.0  # an unchanged word is written again only this often: no write per request
TABLE = """
CREATE TABLE IF NOT EXISTS clients (
    client TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    skill TEXT NOT NULL,
    seen_at REAL NOT NULL
)"""


Said = tuple[str, str, str | None]  # (version, skill, install)


def _checked(version: Any, skill: Any, install: Any, name: str) -> Said:
    if parse(version) is None and not (isinstance(version, str) and 0 < len(version) <= 40):
        raise BadRequest(f"field '{name}' must be a version")
    if skill not in SKILL_STATES:
        raise BadRequest(f"field 'skill' must be one of {', '.join(SKILL_STATES)}")
    if install is not None and install not in upgrade.KINDS:
        raise BadRequest(f"the install must be one of {', '.join(upgrade.KINDS)}")
    return version, skill, install


def fields(body: dict[str, Any]) -> Said | None:
    """(version, skill, install) from a submit body; None when it says none (an older client)."""
    version = body.get("client_version")
    if version is None:
        return None
    return _checked(version, body.get("skill", "none"), body.get("client_install"),
                    "client_version")


def heard(store: Store, body: dict[str, Any], now: float) -> None:
    """Keep what a request's `dev_machine` field says, and take the field off the body, so the
    request reads as before. A bad field is left out, never a refusal: the request is the point."""
    said = body.pop(FIELD, None)
    if said is None or store.readonly:
        return
    try:
        if not isinstance(said, dict) or not isinstance(said.get("client"), str):
            raise BadRequest(f"field '{FIELD}' must name its client")
        client = said["client"][:255]
        word = _checked(said.get("version"), said.get("skill", "none"), said.get("install"),
                        f"{FIELD}.version")
    except BadRequest as exc:
        _log.warning("ignored a dev machine's word: %s", exc)
        return
    with store.read() as conn:
        row = conn.execute("SELECT version, skill, install, seen_at FROM clients WHERE client = ?",
                           (client,)).fetchone()
    if row and tuple(row)[:3] == word and now - row["seen_at"] < REFRESH_S:
        return
    with store.write() as conn:
        seen(conn, client, word, now)


def seen(conn: sqlite3.Connection, client: str, said: Said, now: float) -> None:
    conn.execute("INSERT INTO clients (client, version, skill, install, seen_at) "
                 "VALUES (?, ?, ?, ?, ?) ON CONFLICT(client) DO UPDATE SET "
                 "version = excluded.version, skill = excluded.skill, "
                 "install = excluded.install, seen_at = excluded.seen_at",
                 (client, *said, now))


def recent(conn: sqlite3.Connection, now: float) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM clients WHERE seen_at >= ? ORDER BY client",
                        (now - RECENT_DAYS * 86400.0,))
    return [dict(row) for row in rows]
