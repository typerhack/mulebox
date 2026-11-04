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
  containers and built images. That is what makes them findable after a crash;
- an image the project builds gets a tag only this job has, also where the compose file
  names one, and `build.tags` go. Two jobs would otherwise share `example-app:ci`, one could
  run the other's build, and removing it could take a tag that is not the job's to remove.
  A service that uses any of those names without building it follows the new tag.

What would reach past the job is refused first, by compose_policy.py. A read-only bind of a
path outside the checkout gets `create_host_path: false` as well: Compose would otherwise
create the folder on the machine if it disappeared after the check, and nothing removes it.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mulebox.common import compose
from mulebox.common.compose import ComposeError
from mulebox.worker import compose_policy

Model = dict[str, Any]
LOOPBACK = "127.0.0.1"
PORT_PREFIX = "MULEBOX_PORT_"
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


def _rewrite_ports(spec: Model, assigned: Mapping[str, int], name: str) -> None:
    done, rewritten = set(), []
    for entry, port in zip(spec.get("ports") or [], _ports_of(name, spec)):
        if port.variable not in done:
            done.add(port.variable)
            rewritten.append({**entry, "host_ip": LOOPBACK,
                              "published": str(assigned[port.variable])})
    if rewritten:
        spec["ports"] = rewritten


def _never_create_outside(spec: Model, checkout: Path) -> None:
    for volume in spec.get("volumes") or []:
        source = volume.get("source") or ""
        if volume.get("type") == "bind" and not compose_policy.inside(source, checkout):
            volume["bind"] = {**(volume.get("bind") or {}), "create_host_path": False}


def _rewrite_service(name: str, spec: Model, labels: Mapping[str, str],
                     assigned: Mapping[str, int], checkout: Path, notes: list[str]) -> None:
    spec["labels"] = {**(spec.get("labels") or {}), **labels}
    if isinstance(spec.get("build"), dict):
        spec["build"]["labels"] = {**(spec["build"].get("labels") or {}), **labels}
    _rewrite_ports(spec, assigned, name)
    _never_create_outside(spec, checkout)
    fixed = spec.pop("container_name", None)
    if fixed:
        notes.append(f"container_name {fixed} of service {name} was dropped, so jobs cannot "
                     f"collide; use `docker compose exec -T {name} ...`")


def _plain(image: str) -> str:
    return image.removesuffix(":latest")


def _own_images(services: dict[str, Model], job_id: str, notes: list[str]) -> None:
    owned: dict[str, str] = {}
    for index, (name, spec) in enumerate(services.items(), 1):
        if not spec.get("build"):
            continue
        given = [*filter(None, [spec.get("image")]), *(spec["build"].pop("tags", None) or [])]
        known = (owned[_plain(image)] for image in given if _plain(image) in owned)
        tag = next(known, None) or compose.image_name(job_id, index, name)
        spec["image"] = tag
        for image in given:
            owned.setdefault(_plain(image), tag)
            notes.append(f"the image {image} of service {name} is built as {tag}, so jobs "
                         "cannot share it; use the service name, not the tag")
    for spec in services.values():
        if not spec.get("build") and _plain(spec.get("image") or "") in owned:
            spec["image"] = owned[_plain(spec["image"])]


def _rewrite_section(model: Model, section: str, labels: Mapping[str, str]) -> None:
    project = model["name"]
    for key, spec in (model.get(section) or {}).items():
        spec = spec if spec is not None else {}
        model[section][key] = {**spec, "name": f"{project}_{key}",
                               "labels": {**(spec.get("labels") or {}), **labels}}


def rewrite(model: Model, job_id: str, labels: Mapping[str, str],
            assigned: Mapping[str, int], checkout: Path,
            shared: Sequence[Path] = ()) -> tuple[Model, list[str]]:
    """The model a job runs, plus notes for its log. ComposeError for what is refused."""
    result, notes = copy.deepcopy(model), []
    result["name"] = compose.project_name(job_id)
    compose_policy.check(result, checkout, shared)
    _own_images(_services(result), job_id, notes)
    for name, spec in _services(result).items():
        _rewrite_service(name, spec, labels, assigned, checkout, notes)
    for section in ("networks", "volumes"):
        _rewrite_section(result, section, labels)
    return result, notes
