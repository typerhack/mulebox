"""Turning a project's resolved compose model into the one a job runs. Pure: no Docker here.

`docker compose config --format json` gives the merged model of all `compose:` files, with
every value and path already resolved. This module changes that model so a job cannot
collide with anything else on the machine, and writes nothing itself:

- every published port is bound to 127.0.0.1 on a port mulebox chose, so neither two jobs
  nor a job and a service already on the machine can clash; `MULEBOX_PORT_<SERVICE>_<PORT>`
  tells the job which one it got, and a compose file's own choice of port does not count;
- `container_name` goes, because a fixed name collides with the next job, and with any
  container of that name; the job is told, and `docker compose exec` still finds it;
- networks and named volumes are named after the job's project and carry its labels, as do
  containers and built images. That is what makes them findable after a crash.

It also refuses what would reach past the job: host networking, the host's process or IPC
namespace, `privileged`, external volumes and networks, volumes backed by a host device, the
Docker socket, and writable bind mounts outside the checkout. This guards against a CI
file written for a throwaway runner, not against a hostile project: a job can run any
command, and Docker access is root-equivalent (docs/design.md, Safety).
"""

from __future__ import annotations

import copy
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mulebox.common.compose import ComposeError
from mulebox.common.mounts import is_within

Model = dict[str, Any]
LOOPBACK = "127.0.0.1"
PORT_PREFIX = "MULEBOX_PORT_"
_HOST_NAMESPACES = ("network_mode", "pid", "ipc")
_NOT_A_NAME = re.compile(r"[^A-Za-z0-9]")


@dataclass(frozen=True)
class Port:
    service: str
    target: int
    protocol: str

    @property
    def variable(self) -> str:
        suffix = "" if self.protocol == "tcp" else f"_{self.protocol.upper()}"
        return f"{PORT_PREFIX}{_NOT_A_NAME.sub('_', self.service).upper()}_{self.target}{suffix}"


def _services(model: Model) -> dict[str, Model]:
    services = model.get("services")
    if not isinstance(services, dict) or not services:
        raise ComposeError("the compose files define no services")
    return services


def _ports_of(service: str, spec: Model) -> list[Port]:
    return [Port(service, entry["target"], entry.get("protocol") or "tcp")
            for entry in spec.get("ports") or []]


def published_ports(model: Model) -> list[Port]:
    """Each port the model publishes, once; two host ports for one target become one."""
    ports = [port for name, spec in _services(model).items() for port in _ports_of(name, spec)]
    distinct = list(dict.fromkeys(ports))
    owners: dict[str, Port] = {}
    for port in distinct:
        other = owners.setdefault(port.variable, port)
        if other != port:
            raise ComposeError(f"services {other.service} and {port.service} would both be "
                               f"{port.variable}; rename one of them")
    return distinct


def _bind_problem(volume: Model, checkout: Path) -> str | None:
    source = Path(os.path.realpath(volume.get("source") or ""))
    if source.name == "docker.sock":
        return f"mounts the Docker socket {source}"
    if is_within(source, checkout) or volume.get("read_only"):
        return None
    return (f"bind-mounts {volume.get('source')} writable, outside the checkout. Use a path "
            "in the project, a named volume, or mount it read-only")


def _service_problem(spec: Model, checkout: Path) -> str | None:
    for key in _HOST_NAMESPACES:
        if spec.get(key) == "host":
            return f"uses {key}: host, which would reach past the job"
    if spec.get("privileged"):
        return "is privileged, which would reach past the job"
    for volume in spec.get("volumes") or []:
        problem = _bind_problem(volume, checkout) if volume.get("type") == "bind" else None
        if problem:
            return problem
    return None


def _rewrite_ports(spec: Model, assigned: Mapping[str, int], name: str) -> None:
    done, rewritten = set(), []
    for entry, port in zip(spec.get("ports") or [], _ports_of(name, spec)):
        if port.variable not in done:
            done.add(port.variable)
            rewritten.append({**entry, "host_ip": LOOPBACK,
                              "published": str(assigned[port.variable])})
    if rewritten:
        spec["ports"] = rewritten


def _rewrite_service(name: str, spec: Model, labels: Mapping[str, str],
                     assigned: Mapping[str, int], notes: list[str]) -> None:
    spec["labels"] = {**(spec.get("labels") or {}), **labels}
    if isinstance(spec.get("build"), dict):
        spec["build"]["labels"] = {**(spec["build"].get("labels") or {}), **labels}
    _rewrite_ports(spec, assigned, name)
    fixed = spec.pop("container_name", None)
    if fixed:
        notes.append(f"container_name {fixed} of service {name} was dropped, so jobs cannot "
                     f"collide; use `docker compose exec -T {name} ...`")


def _rewrite_section(model: Model, section: str, labels: Mapping[str, str]) -> None:
    project = model["name"]
    for key, spec in (model.get(section) or {}).items():
        spec = spec if spec is not None else {}
        if spec.get("external"):
            raise ComposeError(f"{section} {key} is external, so jobs would share it; declare "
                               "it in the compose file so each job gets its own")
        if (spec.get("driver_opts") or {}).get("device"):
            raise ComposeError(f"{section} {key} is backed by a host device or folder; use a "
                               "plain named volume")
        model[section][key] = {**spec, "name": f"{project}_{key}",
                               "labels": {**(spec.get("labels") or {}), **labels}}


def rewrite(model: Model, project: str, labels: Mapping[str, str],
            assigned: Mapping[str, int], checkout: Path) -> tuple[Model, list[str]]:
    """The model a job runs, plus notes for its log. ComposeError for what is refused."""
    result, notes = copy.deepcopy(model), []
    result["name"] = project
    for name, spec in _services(result).items():
        problem = _service_problem(spec, checkout)
        if problem:
            raise ComposeError(f"service {name} {problem}")
        _rewrite_service(name, spec, labels, assigned, notes)
    for section in ("networks", "volumes"):
        _rewrite_section(result, section, labels)
    return result, notes
