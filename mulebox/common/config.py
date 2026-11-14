"""Loading and validating mulebox configuration files.

- Project config: ``.mulebox.yml`` in the repository (YAML, ``yaml.safe_load`` only).
- Client config: ``$MULEBOX_CONFIG`` or ``~/.config/mulebox/client.toml`` (TOML).
- Node config: ``~/.config/mulebox/node.toml`` on a node (TOML).

Unknown keys are errors, and every :class:`ConfigError` names the file and the field.

Choices where docs/interfaces.md is silent:

- ``project`` and node ``name`` must match ``[A-Za-z0-9][A-Za-z0-9._-]*``: they end up
  in paths and log lines on nodes.
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
- ``slots`` is at least 1 (default 1; 1..64 when set from afar) and ``priority`` one of
  ``preferred``, ``normal`` (default) and ``fallback``; ``dev`` (default false) keeps every
  job off the node but those sent to it by name (common/node_settings.py); all three can be
  changed from afar (worker/node_file.py).
- ``os`` (project) is ``linux``, ``macos`` or ``any`` (common/systems.py).
  ``[dashboard]`` is read in config_node.py.
- ``retention`` has ``log_days`` (default 30, at least 1) and ``step_days`` (default 365, at
  least ``log_days``).
- ``limits`` has ``unattended_idle_min`` (default 15, at least 1) and ``unattended_max_hours``
  (default 24, at least 1), which must not be shorter than the idle limit.
- An explicit ``path`` argument wins over ``$MULEBOX_CONFIG``; an empty
  ``$MULEBOX_CONFIG`` is ignored.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from mulebox.common import compose, config_jobs, config_node, config_project
from mulebox.common import isolation as isolation_rules
from mulebox.common.config_node import DASHBOARD_MODES, DEFAULT_DASHBOARD_PORT  # noqa: F401
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
DEFAULT_TIMEOUT_MIN = 30
DEFAULT_REMOTE_BIN = "~/.mulebox/bin/mulebox"
DEFAULT_LOG_DAYS = 30
DEFAULT_STEP_DAYS = 365
DEFAULT_UNATTENDED_IDLE_MIN = 15
DEFAULT_UNATTENDED_MAX_HOURS = 24
# Toolchains a Mac node has or lacks by itself, never installed by a job, each also the
# capability it offers: Xcode (worker/xcode.py) and a simulator runtime (worker/simulator.py).
XCODE = "xcode"
SIMULATOR = "simulator"
FOUND_ON_NODE = (XCODE, SIMULATOR)


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
    github_status: bool = False  # post check results to the pushed commit (client/github_status.py)
    env: dict[str, str] = field(default_factory=dict)
    job_options: dict[str, config_jobs.JobOptions] = field(default_factory=dict)
    host_ports: tuple[str, ...] = ()  # of the one job `for_job` gave this for
    isolation: str | None = None  # common/isolation.py; None: the node's floor
    image: str | None = None  # an isolated job's own image, else mulebox's
    system: str | None = None  # `os:`, sent as is; the coordinator adds the need (systems.py)

    @property
    def all_needs(self) -> tuple[str, ...]:
        """`needs`, plus what a `compose:` project cannot run without (common/compose.py), and
        `xcode` or `simulator` for one that pins it: a Mac node that has it offers it. The
        system its jobs run on is the coordinator's to add, from `os:` (common/systems.py)."""
        implied = (compose.DOCKER_CAPABILITY, compose.COMPOSE_CAPABILITY) if self.compose else ()
        implied = (*implied, *(name for name in FOUND_ON_NODE if name in self.toolchain))
        if self.isolation == isolation_rules.CONTAINER:
            implied = (*implied, compose.DOCKER_CAPABILITY, isolation_rules.CAPABILITY)
        elif self.isolation == isolation_rules.NONE:  # asked for: refused on an isolated node
            implied = (*implied, isolation_rules.UNISOLATED)
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
    priority: str = "normal"  # common/node_settings.py
    dev: bool = False  # takes only jobs sent to it by name (common/node_settings.py)
    capabilities: tuple[str, ...] = ()
    isolation: str = isolation_rules.NONE  # the floor for every job here (common/isolation.py)
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
        github_status=reader.boolean("github_status", False),
        env=config_project.env_values(reader, files),
        **config_project.isolation_fields(reader),
        system=config_project.system(reader),
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
    """Load the client config of the dev machine."""
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


def load_node_config(path: Path | None = None) -> NodeConfig:
    """Load a node's config."""
    path = Path(path) if path is not None else node_config_path()
    return node_config_from(path, load_toml(path))


def _floor(reader: Reader) -> str:
    """A node's `isolation`: `container` only where jobs can be isolated."""
    level = reader.text("isolation", isolation_rules.NONE)
    if (problem := isolation_rules.level_problem(level)) is not None:
        reader.fail("isolation", problem)
    if level == isolation_rules.CONTAINER and not isolation_rules.can_isolate(
            reader.strings("capabilities"), compose.DOCKER_CAPABILITY):
        reader.fail("isolation", "container needs a Linux node with Docker and `docker` in "
                    "its capabilities")
    return level


def node_config_from(path: Path, data: Any) -> NodeConfig:
    """A node's config from parsed TOML; `path` names the file in errors."""
    reader = Reader(path, data)
    config = NodeConfig(
        name=reader.name("name"),
        roles=_roles(reader),
        roots=_roots(reader),
        slots=config_node.slots(reader),
        priority=config_node.priority(reader),
        dev=reader.boolean("dev", False),
        capabilities=reader.strings("capabilities"),
        isolation=_floor(reader),
        coordinator=reader.ssh_target("coordinator", None),
        coordinator_key=reader.absolute_path("coordinator_key"),
        dashboard=config_node.dashboard(reader),
        job_env=config_project.job_env(reader),
        retention=config_project.retention(reader, DEFAULT_LOG_DAYS, DEFAULT_STEP_DAYS),
        limits=config_project.limits(reader, DEFAULT_UNATTENDED_IDLE_MIN,
                                     DEFAULT_UNATTENDED_MAX_HOURS),
    )
    reader.finish()
    if config.dev and "coordinator" in config.roles:
        reader.fail("dev", "is for other nodes: this one is the coordinator, which every job "
                    "goes through")
    if config.coordinator is None and "coordinator" not in config.roles:
        reader.fail("coordinator", "is required on a node without the 'coordinator' role")
    return config
