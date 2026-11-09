"""What is out of step, for the strip above the dashboard's panels: each a problem and its fix.

Three kinds, from what the build machine already knows: a worker on another mulebox than the
coordinator, a laptop on another mulebox than the build machine (coordinator/clients.py), and a
laptop whose agent skill is out of date. Nothing here guesses at a release nobody has made: a
notice is only ever two real installs that disagree. Empty when all is in step.
"""

from __future__ import annotations

from typing import Any

from mulebox.common.versions import compare
from mulebox.coordinator.workers import is_online


def _worker(worker: dict[str, Any], version: str) -> dict[str, str] | None:
    found = worker.get("version")
    if not found or found == version:
        return None
    return {"kind": "worker", "name": worker["worker"],
            "text": f"Worker {worker['worker']} runs mulebox {found}, the coordinator {version}.",
            "fix": "Run `mulebox setup` for it from a laptop on the current mulebox."}


def _client(client: dict[str, Any], version: str) -> list[dict[str, str]]:
    out, name, found = [], client["client"], client["version"]
    order = compare(found, version)
    if found != version:
        newer = order == 1
        out.append({"kind": "client", "name": name,
                    "text": f"Laptop {name} runs mulebox {found}, the build machine {version}.",
                    "fix": ("Run `mulebox setup <host>` from it to bring the machine up."
                            if newer else "Upgrade mulebox on it.")})
    if client["skill"] == "out_of_date":
        out.append({"kind": "skill", "name": name,
                    "text": f"The mulebox skill on {name} is out of date.",
                    "fix": "Run `mulebox skill update` there; an agent does it when "
                           "`mulebox contract` tells it."})
    return out


def notices(version: str, workers: list[dict[str, Any]], clients: list[dict[str, Any]],
            now: float) -> list[dict[str, str]]:
    found = [n for w in workers if is_online(w, now) and (n := _worker(w, version))]
    return found + [n for client in clients for n in _client(client, version)]
