"""What a job's compose model may not do: reach past the job. Pure checks, nothing changes.

The model comes from `docker compose config`, so every value is resolved and `extends` and
`include` are already merged in. A job's containers should see the job and nothing else, so
this refuses what opens a door out of that: the host's namespaces and those of containers
outside the project, devices, extra kernel powers, inherited mounts, the Docker API, host
paths that Compose would create or write, and build features that do the same for a build.

Refused, not repaired: the project's owner decides what to do, and the message says why.
This guards against a CI file written for a throwaway runner, not against a hostile project:
a job can run any command, and Docker access is root-equivalent (docs/design.md, Safety).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

from mulebox.common.compose import ComposeError
from mulebox.common.mounts import is_within

Model = dict[str, Any]

_NAMESPACES = ("network_mode", "pid", "ipc", "uts", "userns_mode", "cgroup")
_FOREIGN_NAMESPACE = ("container:", "ns:")
_SERVICE_NAMESPACE = "service:"
_REFUSED_KEYS = {
    "privileged": "is privileged",
    "devices": "uses host devices (devices:)",
    "device_cgroup_rules": "changes which host devices it may use",
    "gpus": "uses host GPUs",
    "cgroup_parent": "picks its own control group",
    "external_links": "links to containers outside the project",
    "use_api_socket": "gets the Docker API",
    "provider": "runs a program on the build machine (provider:)",
    "runtime": "picks its own container runtime",
}
_HOOKS = ("pre_start", "post_start", "pre_stop")
_VOLUME_TYPES = (None, "bind", "volume", "tmpfs", "image")
# Docker's default set, which `cap_drop: [ALL]` files add back, and three that databases and
# search engines ask for and that stay inside the container.
_CAPABILITIES = frozenset({
    "AUDIT_WRITE", "CHOWN", "DAC_OVERRIDE", "FOWNER", "FSETID", "KILL", "MKNOD",
    "NET_BIND_SERVICE", "NET_RAW", "SETFCAP", "SETGID", "SETPCAP", "SETUID", "SYS_CHROOT",
    "IPC_LOCK", "SYS_NICE", "SYS_PTRACE",
})
_SECURITY_OPT_ALLOWED = "no-new-privileges"
_BUILD_REFUSED = {
    "privileged": "is privileged",
    "entitlements": "asks for build entitlements",
    "ssh": "forwards an SSH agent",
    "cache_to": "writes its cache outside the job (cache_to:)",
}
_DEPLOY_REFUSED = ("devices", "generic_resources")
# Only for a folder as a source: a socket itself is found by its type. A folder can be huge,
# so these are the places to look at, on both spellings of the run directory.
_RUNTIME_SOCKETS = tuple(f"{run}/{socket}" for run in ("/run", "/var/run") for socket in (
    "docker.sock", "containerd/containerd.sock", "crio/crio.sock", "podman/podman.sock",
    "k3s/containerd/containerd.sock", "cri-dockerd.sock", "buildkit/buildkitd.sock",
    f"user/{os.getuid()}/docker.sock", f"user/{os.getuid()}/podman/podman.sock"))
_RUN_FOLDERS = ("/run", "/var/run")
_NETWORK_DRIVERS = (None, "bridge", "default")
_VOLUME_DRIVERS = (None, "local")


def _is_socket(path: Path) -> bool:
    try:
        return stat.S_ISSOCK(os.stat(path).st_mode)
    except OSError:
        return False


def _holds_socket(source: Path) -> bool:
    """True if `source` is a Unix socket of any kind, or a folder holding a runtime's socket.
    A read-only mount does not stop anyone talking to a socket. A known socket may be a
    symlink, or its folder may be, so what they lead to counts as well."""
    if _is_socket(source):
        return True
    if any(is_within(source, Path(os.path.realpath(run))) for run in _RUN_FOLDERS):
        return True  # sockets live here under names no list can hold
    spots = {Path(path) for path in _RUNTIME_SOCKETS}
    spots |= {Path(os.path.realpath(path)) for path in _RUNTIME_SOCKETS}
    spots |= {Path(os.path.realpath(os.path.dirname(path))) / Path(path).name
              for path in _RUNTIME_SOCKETS}
    return any(is_within(spot, source) for spot in spots)


def _outside_problem(path: str) -> str | None:
    """Reading this host path from a job: what is wrong with it, or None."""
    if _holds_socket(Path(os.path.realpath(path))):
        return f"mounts a container runtime or other Unix socket through {path}"
    return None


def inside(path: str, checkout: Path) -> bool:
    return is_within(Path(os.path.realpath(path)), checkout)


def _bind_problem(volume: Model, checkout: Path) -> str | None:
    path = volume.get("source") or ""
    problem = _outside_problem(path)
    if problem:
        return problem
    if inside(path, checkout):
        return None
    if not os.path.exists(path):
        return (f"bind-mounts {path}, outside the checkout, and it does not exist on the "
                "build machine. mulebox does not create folders there")
    if not volume.get("read_only"):
        return (f"bind-mounts {path} writable, outside the checkout. Use a path in the "
                "project, a named volume, or mount it read-only")
    if (volume.get("bind") or {}).get("selinux"):
        return f"relabels {path}, outside the checkout"
    return None


def _volume_problem(volume: Model, checkout: Path) -> str | None:
    kind = volume.get("type")
    if kind not in _VOLUME_TYPES:
        return f"uses a {kind} volume, which would reach past the job"
    return _bind_problem(volume, checkout) if kind == "bind" else None


def _inherited_problem(entry: str, services: Model) -> str | None:
    if entry.startswith("container:"):
        return f"inherits the mounts of a container outside the project ({entry})"
    name = entry.split(":", 1)[0]
    return None if name in services else f"inherits mounts from unknown service {name}"


def _namespace_problem(key: str, value: Any, services: Model) -> str | None:
    text = str(value or "")
    if text == "host" or text.startswith(_FOREIGN_NAMESPACE):
        return f"uses {key}: {text}, which would reach past the job"
    if text.startswith(_SERVICE_NAMESPACE) and text.split(":", 1)[1] not in services:
        return f"uses {key}: {text}, which is no service of this project"
    return None


def _capability_problem(names: list[str]) -> str | None:
    for name in names:
        bare = str(name).upper().removeprefix("CAP_")
        if bare not in _CAPABILITIES:
            return f"adds the capability {name}, which would reach past the job"
    return None


def _security_problem(options: list[str]) -> str | None:
    for option in options:
        if not str(option).startswith(_SECURITY_OPT_ALLOWED):
            return f"changes container security ({option}), which would reach past the job"
    return None


def _build_problem(build: Any) -> str | None:
    if not isinstance(build, dict):
        return None
    if build.get("network") == "host":
        return "builds with network: host, which would reach past the job"
    for key, reason in _BUILD_REFUSED.items():
        if build.get(key):
            return f"has a build that {reason}, which would reach past the job"
    return None


def _deploy_problem(spec: Model) -> str | None:
    resources = (spec.get("deploy") or {}).get("resources") or {}
    for kind in ("limits", "reservations"):
        for key in _DEPLOY_REFUSED:
            if (resources.get(kind) or {}).get(key):
                return f"asks for host hardware in deploy ({kind}.{key}), which would reach past the job"
    return None


def _hook_problem(spec: Model) -> str | None:
    for key in _HOOKS:
        if any(hook.get("privileged") for hook in spec.get(key) or []):
            return f"has a privileged {key} hook, which would reach past the job"
    return None


def _service_problem(spec: Model, services: Model, checkout: Path) -> str | None:
    for key, reason in _REFUSED_KEYS.items():
        if spec.get(key):
            return f"{reason}, which would reach past the job"
    for key in _NAMESPACES:
        problem = _namespace_problem(key, spec.get(key), services)
        if problem:
            return problem
    for volume in spec.get("volumes") or []:
        problem = _volume_problem(volume, checkout)
        if problem:
            return problem
    for entry in spec.get("volumes_from") or []:
        problem = _inherited_problem(entry, services)
        if problem:
            return problem
    return (_capability_problem(spec.get("cap_add") or [])
            or _security_problem(spec.get("security_opt") or [])
            or _build_problem(spec.get("build"))
            or _deploy_problem(spec)
            or _hook_problem(spec))


def _section_problem(section: str, key: str, spec: Model) -> str | None:
    if spec.get("external"):
        return (f"{section} {key} is external, so jobs would share it; declare it in the "
                "compose file so each job gets its own")
    if section == "networks" and spec.get("driver") not in _NETWORK_DRIVERS:
        return f"network {key} uses the {spec['driver']} driver; use a plain bridge network"
    if section == "volumes":
        if spec.get("driver") not in _VOLUME_DRIVERS:
            return f"volume {key} uses the {spec['driver']} driver; use a plain named volume"
        if (spec.get("driver_opts") or {}).get("device"):
            return f"volume {key} is backed by a host device or folder; use a plain named volume"
    return None


def _file_problem(section: str, key: str, spec: Model, checkout: Path) -> str | None:
    if spec.get("external"):
        return f"{section} {key} is external, which a job cannot have"
    path = spec.get("file")
    if not path:
        return None
    problem = _outside_problem(path)
    if not problem and not inside(path, checkout) and not os.path.exists(path):
        problem = f"reads {path}, outside the checkout, and it does not exist"
    return f"{section} {key} {problem}" if problem else None


def check(model: Model, checkout: Path) -> None:
    """ComposeError naming the first thing in `model` that reaches past the job."""
    services = model.get("services") or {}
    for name, spec in services.items():
        problem = _service_problem(spec, services, checkout)
        if problem:
            raise ComposeError(f"service {name} {problem}")
    for section in ("networks", "volumes"):
        for key, spec in (model.get(section) or {}).items():
            problem = _section_problem(section, key, spec or {})
            if problem:
                raise ComposeError(problem)
    for section in ("secrets", "configs"):
        for key, spec in (model.get(section) or {}).items():
            problem = _file_problem(section, key, spec or {}, checkout)
            if problem:
                raise ComposeError(problem)
