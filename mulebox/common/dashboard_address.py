"""Where a person can see the dashboard: told by the node, printed by the client.

The address lives in the node's `node.toml`, so the coordinator puts `where` into its
replies and the client turns it into `hint`. `None` means nothing to say: the dashboard is off,
or the coordinator is too old to send this.
"""

from __future__ import annotations

from typing import Any

JOB_ROUTE = "/#/job/"


def where(dashboard: dict[str, Any]) -> dict[str, Any] | None:
    """The `dashboard` reply field for a node's `[dashboard]` settings."""
    mode = dashboard.get("mode")
    if mode == "lan":
        scheme = "https" if dashboard.get("lan_tls") else "http"
        return {"url": f"{scheme}://{dashboard['lan_address']}:{dashboard['lan_port']}"}
    return {"url": None} if mode == "local" else None


def place(info: Any, job_id: str | None = None) -> str | None:
    """A URL, a job's page in it, or the command that opens the dashboard through a tunnel."""
    if not isinstance(info, dict):
        return None
    url = info.get("url")
    if not isinstance(url, str) or not url:
        return "mulebox dashboard open"
    return f"{url}{JOB_ROUTE}{job_id}" if job_id else url


def hint(info: Any, job_id: str | None = None) -> str | None:
    """One line for a person, or None when there is nothing to point at."""
    found = place(info, job_id)
    return f"see it on the dashboard: {found}" if found else None
