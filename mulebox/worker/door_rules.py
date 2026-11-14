"""What an isolated job may ask of Docker through its door (docker_door.py; docs/design.md,
Isolation per job, way 2). Pure decisions, no I/O.

A job line such as `docker compose exec -T api pytest` must work, and nothing that would reach
past the job: no new container, image, volume or network, no copy in or out, no other job's or
the node's containers. So the door answers only these, with the API version prefix stripped:

- `_ping`, `version` and `info`, which the CLI asks before anything;
- the list of containers, narrowed to this job's by a label filter added to the query;
- for one container, only after the door has seen the job's label on it: inspect, logs, top,
  wait, start, stop, restart, kill, and making an exec in it (never a privileged one);
- an exec the door itself made for this job: start, inspect, resize.

Anything else is refused with a message that names the call.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit

_VERSION = re.compile(r"^/v[0-9]+\.[0-9]+(?=/)")
_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}"
_OPEN = {("GET", "/_ping"), ("HEAD", "/_ping"), ("GET", "/version"), ("GET", "/info")}
_CONTAINER = re.compile(rf"^/containers/({_ID})/(json|logs|top|wait|start|stop|restart|kill|exec)$")
_CONTAINER_METHODS = {"json": "GET", "logs": "GET", "top": "GET", "wait": "POST",
                      "start": "POST", "stop": "POST", "restart": "POST", "kill": "POST",
                      "exec": "POST"}
_EXEC = re.compile(rf"^/exec/({_ID})/(start|json|resize)$")
_EXEC_METHODS = {"start": "POST", "json": "GET", "resize": "POST"}


@dataclass(frozen=True)
class Decision:
    """`allow`: pass it on (to `target`, the request path to send). `container`: allowed only
    once that container shows the job's label. `exec_create`: the reply holds an exec id to
    remember. `why`: the refusal's message."""
    allow: bool
    target: str = ""
    container: str | None = None
    exec_id: str | None = None
    exec_create: bool = False
    why: str = ""


def refuse(method: str, path: str) -> Decision:
    return Decision(False, why=f"mulebox: an isolated job may not ask Docker for {method} "
                               f"{path}: only exec, logs, inspect, start, stop and restart "
                               "of its own containers (docs/design.md, Isolation per job)")


def _job_list(query: str, label: str) -> str:
    """The containers query with this job's label added to its filters."""
    params = parse_qsl(query, keep_blank_values=True)
    filters: dict[str, list[str]] = {}
    rest = []
    for key, value in params:
        if key != "filters":
            rest.append((key, value))
            continue
        try:
            given = json.loads(value)
        except ValueError:
            given = {}
        for name, values in (given.items() if isinstance(given, dict) else ()):
            # Docker takes both ["a", "b"] and {"a": true, "b": true}
            items = list(values) if isinstance(values, (list, dict)) else []
            filters.setdefault(str(name), []).extend(str(item) for item in items)
    filters.setdefault("label", []).append(label)
    return urlencode([*rest, ("filters", json.dumps(filters))])


def decide(method: str, raw_path: str, job_label: str, execs: set[str]) -> Decision:
    """What to do with one request. `job_label`: `mulebox.job=<id>`; `execs`: exec ids the door
    made for this job."""
    parts = urlsplit(raw_path)
    version = _VERSION.match(parts.path)
    prefix = version.group(0) if version else ""
    path = parts.path[len(prefix):]
    if (method, path) in _OPEN:
        return Decision(True, target=raw_path)
    if method == "GET" and path == "/containers/json":
        return Decision(True, target=f"{prefix}{path}?{_job_list(parts.query, job_label)}")
    if (found := _CONTAINER.match(path)) and _CONTAINER_METHODS[found.group(2)] == method:
        return Decision(True, target=raw_path, container=found.group(1),
                        exec_create=found.group(2) == "exec")
    if (found := _EXEC.match(path)) and _EXEC_METHODS[found.group(2)] == method:
        if found.group(1) in execs:
            return Decision(True, target=raw_path, exec_id=found.group(1))
    return refuse(method, path)


def exec_body_problem(body: bytes) -> str | None:
    """Why an exec's settings are refused: a privileged exec has every kernel power the
    container was not given."""
    try:
        config = json.loads(body or b"{}")
    except ValueError:
        return "mulebox: the exec's settings are not JSON"
    if not isinstance(config, dict):
        return "mulebox: the exec's settings are not an object"
    if config.get("Privileged"):
        return "mulebox: an isolated job may not make a privileged exec"
    return None


def has_label(inspect_body: bytes, job_label: str) -> bool:
    """Whether a container's inspect reply carries the job's label."""
    try:
        labels = (json.loads(inspect_body).get("Config") or {}).get("Labels") or {}
    except (ValueError, AttributeError):
        return False
    key, _, value = job_label.partition("=")
    return isinstance(labels, dict) and labels.get(key) == value
