"""Loading and validating mulebox configuration files.

- Project config: ``.mulebox.yml`` in the repository (YAML, ``yaml.safe_load`` only).
- Client config: ``$MULEBOX_CONFIG`` or ``~/.config/mulebox/client.toml`` (TOML).
- Node config: ``~/.config/mulebox/node.toml`` on a build machine (TOML).

Unknown keys are errors, and every :class:`ConfigError` names the file and the field.

Choices where docs/interfaces.md is silent:

- ``project`` and node ``name`` must match ``[A-Za-z0-9][A-Za-z0-9._-]*``: they end up
  in paths and log lines on build machines.
- Toolchain versions must be YAML strings; an unquoted ``3.10`` would load as the float
  ``3.1``, so it is rejected with a hint to quote it.
- List fields must be lists (a bare string is rejected). Both ``services`` and
  ``compose`` may be set.
- ``connect_timeout_s`` is 1..300 and ``dashboard.port`` 1..65535.
- ssh targets (``coordinator``) must be non-empty, without whitespace, and must not start
  with ``-`` so they can never be read as an ssh option.
- ``roles`` is a non-empty list without duplicates. A node without the ``coordinator``
  role must set ``coordinator`` (the ssh target of the coordinator machine).
- ``roots`` needs all of ``jobs``, ``cache``, ``staging``, ``runners``; each must be
  absolute, not ``/`` and without ``..`` components.
- ``dashboard`` defaults to ``mode = "local"``, ``port = 8090``, ``lan_range = None``;
  ``mode = "lan"`` requires ``lan_range``, which must be a network in CIDR form with an
  explicit prefix length (a bare address, or host bits set as in ``192.168.1.5/24``, is
  an error). ``lan_range`` is normalised
  to its string form, e.g. ``192.168.1.0/24``.
- An explicit ``path`` argument wins over ``$MULEBOX_CONFIG``; an empty
  ``$MULEBOX_CONFIG`` is ignored.
"""

from __future__ import annotations

import re
import ipaddress
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from mulebox.common.config_reader import ConfigError, Reader, load_toml, load_yaml

__all__ = [
    "ClientConfig",
    "ConfigError",
    "NodeConfig",
    "ProjectConfig",
    "client_config_path",
    "find_project_config",
    "load_client_config",
    "load_node_config",
    "load_project_config",
    "node_config_path",
]

PROJECT_FILE = ".mulebox.yml"
CLIENT_ENV = "MULEBOX_CONFIG"
ROLES = ("coordinator", "worker")
ROOT_KEYS = ("jobs", "cache", "staging", "runners")
DASHBOARD_MODES = ("off", "local", "lan")
DEFAULT_TIMEOUT_MIN = 30
DEFAULT_REMOTE_BIN = "~/.mulebox/bin/mulebox"
DEFAULT_DASHBOARD_PORT = 8090


@dataclass(frozen=True)
class ProjectConfig:
    project: str
    jobs: dict[str, str]
    needs: tuple[str, ...] = ()
    toolchain: dict[str, str] = field(default_factory=dict)
    setup: str | None = None
    services: tuple[str, ...] = ()
    compose: tuple[str, ...] = ()
    timeout_min: int = DEFAULT_TIMEOUT_MIN
    exclude: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ClientConfig:
    coordinator: str
    remote_bin: str = DEFAULT_REMOTE_BIN
    connect_timeout_s: int = 10


@dataclass(frozen=True)
class NodeConfig:
    name: str
    roles: tuple[str, ...]
    roots: dict[str, str]
    slots: int = 1
    capabilities: tuple[str, ...] = ()
    coordinator: str | None = None
    dashboard: dict[str, Any] = field(default_factory=dict)


def find_project_config(start: Path) -> Path:
    """Return the nearest ``.mulebox.yml`` at or above ``start``."""
    start = Path(start).resolve()
    directory = start if start.is_dir() else start.parent
    for candidate_dir in (directory, *directory.parents):
        candidate = candidate_dir / PROJECT_FILE
        if candidate.is_file():
            return candidate
    raise ConfigError(directory, None, f"no {PROJECT_FILE} here or in any parent directory")


def _jobs(reader: Reader) -> dict[str, str]:
    jobs = reader.string_map("jobs", required=True)
    if "check" not in jobs:
        reader.fail("jobs", "must define a 'check' job")
    return jobs


def load_project_config(path: Path) -> ProjectConfig:
    """Load and validate a ``.mulebox.yml``."""
    path = Path(path)
    reader = Reader(path, load_yaml(path))
    config = ProjectConfig(
        project=reader.name("project"),
        needs=reader.strings("needs"),
        toolchain=reader.string_map("toolchain"),
        setup=reader.text("setup", None),
        services=reader.strings("services"),
        compose=reader.strings("compose"),
        jobs=_jobs(reader),
        timeout_min=reader.integer("timeout_min", DEFAULT_TIMEOUT_MIN, 1, 240),
        exclude=reader.strings("exclude"),
        env=_env(reader),
    )
    reader.finish()
    return config


_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ENV_RESERVED = ("PATH", "HOME", "USER", "SHELL")


def _env(reader: Reader) -> dict[str, str]:
    """`env:` values for the job: throwaway CI values; names checked, no overriding PATH/HOME."""
    env = reader.string_map("env")
    for key in env:
        if not _ENV_NAME.fullmatch(key):
            reader.fail(f"env.{key}", "must be a shell variable name (letters, digits, _)")
        if key in _ENV_RESERVED or key.startswith("MULEBOX"):
            reader.fail(f"env.{key}", "is set by mulebox or the build machine; choose another name")
    return env


def client_config_path() -> Path:
    """``$MULEBOX_CONFIG`` if set, else ``~/.config/mulebox/client.toml``."""
    override = os.environ.get(CLIENT_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "mulebox" / "client.toml"


def node_config_path() -> Path:
    """``~/.config/mulebox/node.toml``."""
    return Path.home() / ".config" / "mulebox" / "node.toml"


def load_client_config(path: Path | None = None) -> ClientConfig:
    """Load the laptop-side client config."""
    path = Path(path) if path is not None else client_config_path()
    reader = Reader(path, load_toml(path))
    config = ClientConfig(
        coordinator=reader.ssh_target("coordinator"),
        remote_bin=reader.text("remote_bin", DEFAULT_REMOTE_BIN),
        connect_timeout_s=reader.integer("connect_timeout_s", 10, 1, 300),
    )
    reader.finish()
    return config


def _roles(reader: Reader) -> tuple[str, ...]:
    roles = reader.strings("roles")
    if not roles:
        reader.fail("roles", f"must list at least one of {', '.join(ROLES)}")
    for role in roles:
        if role not in ROLES:
            reader.fail("roles", f"unknown role {role!r}; expected {' or '.join(ROLES)}")
    if len(set(roles)) != len(roles):
        reader.fail("roles", "lists a role twice")
    return roles


def _roots(reader: Reader) -> dict[str, str]:
    sub = reader.table("roots", required=True)
    roots = {key: sub.text(key) for key in ROOT_KEYS}
    sub.finish()
    for key, value in roots.items():
        pure = PurePosixPath(value)
        if not pure.is_absolute():
            sub.fail(key, f"must be an absolute path, got {value!r}")
        if pure == PurePosixPath("/") or ".." in pure.parts:
            sub.fail(key, f"must be a directory below '/' without '..', got {value!r}")
    return roots


def _dashboard(reader: Reader) -> dict[str, Any]:
    sub = reader.table("dashboard")
    mode = sub.text("mode", "local")
    if mode not in DASHBOARD_MODES:
        sub.fail("mode", f"must be one of {', '.join(DASHBOARD_MODES)}, got {mode!r}")
    port = sub.integer("port", DEFAULT_DASHBOARD_PORT, 1, 65535)
    lan_range = sub.text("lan_range", None)
    if lan_range is not None:
        if "/" not in lan_range:
            hint = f"needs a prefix length, e.g. 192.168.1.0/24, got {lan_range!r}"
            sub.fail("lan_range", hint)
        try:
            lan_range = str(ipaddress.ip_network(lan_range, strict=True))
        except ValueError as exc:
            sub.fail("lan_range", f"must be a network in CIDR form: {exc}")
    elif mode == "lan":
        sub.fail("lan_range", "is required when mode is 'lan'")
    sub.finish()
    return {"mode": mode, "port": port, "lan_range": lan_range}


def load_node_config(path: Path | None = None) -> NodeConfig:
    """Load a build machine's node config."""
    path = Path(path) if path is not None else node_config_path()
    reader = Reader(path, load_toml(path))
    config = NodeConfig(
        name=reader.name("name"),
        roles=_roles(reader),
        roots=_roots(reader),
        slots=reader.integer("slots", 1, 1),
        capabilities=reader.strings("capabilities"),
        coordinator=reader.ssh_target("coordinator", None),
        dashboard=_dashboard(reader),
    )
    reader.finish()
    if config.coordinator is None and "coordinator" not in config.roles:
        reader.fail("coordinator", "is required on a node without the 'coordinator' role")
    return config
