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
- List fields must be lists (a bare string is rejected).
- ``compose`` lists files that must exist next to ``.mulebox.yml``; the project then needs
  a worker with the ``docker`` capability (:attr:`ProjectConfig.all_needs`), and ``env`` may
  not set the ``COMPOSE_*`` names mulebox sets. ``services`` is refused: nothing starts
  services by name, and a field that does nothing must not look as if it worked.
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
  an error) and a private range. ``lan_range`` is normalised to its string form, e.g.
  ``192.168.1.0/24``. ``lan`` also requires ``lan_address``, this machine's IPv4 address
  inside ``lan_range``; ``lan_port`` defaults to ``port``, the same number on another address;
  ``lan_tls`` defaults to false, ``lan_password`` to true. ``controls`` (default true) gives the
  dashboard its buttons: cancel, pause, resume, first, boost, and pausing a machine.
  ``cancel_button``, from before 0.87.0, is read and ignored.
- ``retention`` has ``log_days`` (default 30, at least 1) and ``step_days`` (default 365, at
  least ``log_days``).
- ``limits`` has ``unattended_idle_min`` (default 15, at least 1) and ``unattended_max_hours``
  (default 24, at least 1), which must not be shorter than the idle limit.
- An explicit ``path`` argument wins over ``$MULEBOX_CONFIG``; an empty
  ``$MULEBOX_CONFIG`` is ignored.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from mulebox.common import compose, config_jobs, config_project
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
DEFAULT_LOG_DAYS = 30
DEFAULT_STEP_DAYS = 365
DEFAULT_UNATTENDED_IDLE_MIN = 15
DEFAULT_UNATTENDED_MAX_HOURS = 24


@dataclass(frozen=True)
class ProjectConfig:
    project: str
    jobs: dict[str, str]
    needs: tuple[str, ...] = ()
    toolchain: dict[str, str] = field(default_factory=dict)
    setup: str | None = None
    install: str | None = None
    compose: tuple[str, ...] = ()
    timeout_min: int = DEFAULT_TIMEOUT_MIN
    exclude: tuple[str, ...] = ()
    ignore_changes: tuple[str, ...] = ()  # paths whose changes never change a result
    env: dict[str, str] = field(default_factory=dict)
    job_options: dict[str, config_jobs.JobOptions] = field(default_factory=dict)
    host_ports: tuple[str, ...] = ()  # of the one job `for_job` gave this for

    @property
    def all_needs(self) -> tuple[str, ...]:
        """`needs`, plus what a `compose:` project cannot run without (common/compose.py)."""
        implied = (compose.DOCKER_CAPABILITY, compose.COMPOSE_CAPABILITY) if self.compose else ()
        return tuple(dict.fromkeys((*self.needs, *implied)))


@dataclass(frozen=True)
class ClientConfig:
    coordinator: str
    remote_bin: str = DEFAULT_REMOTE_BIN
    connect_timeout_s: int = 10
    feedback_repo: str | None = None
    feedback_off: tuple[str, ...] = ()  # projects whose problems are never posted


@dataclass(frozen=True)
class NodeConfig:
    name: str
    roles: tuple[str, ...]
    roots: dict[str, str]
    slots: int = 1
    capabilities: tuple[str, ...] = ()
    coordinator: str | None = None
    coordinator_key: str | None = None  # a worker's own key for it (`mulebox setup --worker-of`)
    dashboard: dict[str, Any] = field(default_factory=dict)
    job_env: dict[str, str] = field(default_factory=dict)
    retention: dict[str, int] = field(default_factory=dict)
    limits: dict[str, int] = field(default_factory=dict)


class ProjectNotFound(ConfigError):
    """No `.mulebox.yml` at or above the folder. A broken one is a plain ConfigError."""


def find_project_config(start: Path) -> Path:
    """Return the nearest ``.mulebox.yml`` at or above ``start``."""
    start = Path(start).resolve()
    directory = start if start.is_dir() else start.parent
    for candidate_dir in (directory, *directory.parents):
        candidate = candidate_dir / PROJECT_FILE
        if candidate.is_file():
            return candidate
    raise ProjectNotFound(directory, None,
                          f"no {PROJECT_FILE} here or in any parent directory")


def load_project_config(path: Path) -> ProjectConfig:
    """Load and validate a ``.mulebox.yml``."""
    path = Path(path)
    reader = Reader(path, load_yaml(path))
    if "services" in reader.data:
        reader.fail("services", "is not supported: nothing would start them. Use compose: to "
                    "run containers for the job, or env: to reach a service by address")
    files = config_project.compose_files(reader, path.parent, PROJECT_FILE)
    jobs, options = config_jobs.read_jobs(reader)
    config = ProjectConfig(
        project=reader.name("project"),
        needs=reader.strings("needs"),
        toolchain=reader.string_map("toolchain"),
        setup=reader.text("setup", None),
        install=reader.text("install", None),
        compose=files,
        jobs=jobs,
        job_options=options,
        timeout_min=reader.integer("timeout_min", DEFAULT_TIMEOUT_MIN, 1, 240),
        exclude=reader.strings("exclude"),
        ignore_changes=reader.strings("ignore_changes"),
        env=config_project.env_values(reader, files),
    )
    reader.finish()
    return config


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
        feedback_repo=reader.text("feedback_repo", None),
        feedback_off=reader.strings("feedback_off"),
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
    if "projects" in sub.data:  # optional: beside `jobs` otherwise (worker/paths.py)
        roots["projects"] = sub.text("projects")
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
    lan_address = sub.text("lan_address", None)
    lan_port = sub.integer("lan_port", port, 1, 65535)
    lan_tls = sub.boolean("lan_tls", False)
    lan_password = sub.boolean("lan_password", True)
    controls = sub.boolean("controls", True)
    sub.boolean("cancel_button", False)  # before 0.87.0; the controls replaced it
    if lan_range is not None:
        if "/" not in lan_range:
            hint = f"needs a prefix length, e.g. 192.168.1.0/24, got {lan_range!r}"
            sub.fail("lan_range", hint)
        try:
            lan_range = str(ipaddress.ip_network(lan_range, strict=True))
        except ValueError as exc:
            sub.fail("lan_range", f"must be a network in CIDR form: {exc}")
        if not ipaddress.ip_network(lan_range).is_private:
            sub.fail("lan_range", f"must be a private network, got {lan_range!r}")
    elif mode == "lan":
        sub.fail("lan_range", "is required when mode is 'lan'")
    if lan_address is not None:
        lan_address = _lan_address(sub, lan_address, lan_range)
    elif mode == "lan":
        sub.fail("lan_address", "is required when mode is 'lan'")
    sub.finish()
    return {"mode": mode, "port": port, "lan_range": lan_range, "lan_address": lan_address,
            "lan_port": lan_port, "lan_tls": lan_tls, "lan_password": lan_password,
            "controls": controls}


def _lan_address(sub, text: str, lan_range: str | None) -> str:
    """This machine's address on the LAN: one IPv4 address, inside `lan_range`."""
    try:
        address = ipaddress.IPv4Address(text)
    except ValueError:
        sub.fail("lan_address", f"must be an IPv4 address, got {text!r}")
    if lan_range is None:
        sub.fail("lan_range", "is required when lan_address is set")
    network = ipaddress.ip_network(lan_range)
    if network.version != 4 or address not in network:
        sub.fail("lan_address", f"{text} is not inside lan_range {lan_range}")
    if address.is_unspecified or address.is_loopback:
        # The sign-in applies by the listener's address: on these it would not apply at all.
        sub.fail("lan_address", f"must be this machine's address on the LAN, got {text}")
    return str(address)


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
        coordinator_key=reader.absolute_path("coordinator_key"),
        dashboard=_dashboard(reader),
        job_env=config_project.job_env(reader),
        retention=config_project.retention(reader, DEFAULT_LOG_DAYS, DEFAULT_STEP_DAYS),
        limits=config_project.limits(reader, DEFAULT_UNATTENDED_IDLE_MIN,
                                     DEFAULT_UNATTENDED_MAX_HOURS),
    )
    reader.finish()
    if config.coordinator is None and "coordinator" not in config.roles:
        reader.fail("coordinator", "is required on a node without the 'coordinator' role")
    return config
