"""Work out a project's `.mulebox.yml` from the files it already has.

Reads manifests, and asks this computer's node and pnpm for their versions; runs nothing of
the project's. Each language gives its install step and its checks; a project with several
gets them all, and one with no checks at its root is looked for one folder down, so
`api/` and `web/` both count. A guess the user must look at goes in `notes`, and only an exact
version is ever pinned as a toolchain.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mulebox.common import package_cache

LOCKFILES = (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("package-lock.json", "npm"))
INSTALL = {"pnpm": "pnpm install --frozen-lockfile", "npm": "npm ci",
           "yarn": "yarn install --frozen-lockfile"}
CACHE = {"pnpm": package_cache.PNPM, "npm": package_cache.NPM}
SCRIPTS = (("lint", "lint"), ("typecheck", "typecheck"), ("type-check", "typecheck"),
           ("test", "test"))
COMPOSE_FILES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
NO_TEST_SCRIPT = "no test specified"
NOT_PROJECTS = frozenset({"node_modules", "vendor", "dist", "build", "target", "docs"})
VERSION_TIMEOUT_S = 5
_EXACT = re.compile(r"v?(\d+\.\d+\.\d+)")
_PACKAGE_MANAGER = re.compile(r"(pnpm|npm|yarn)@(\d+\.\d+\.\d+)")
_NOT_A_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class Detected:
    project: str
    toolchain: dict[str, str] = field(default_factory=dict)
    needs: list[str] = field(default_factory=list)
    compose: list[str] = field(default_factory=list)
    setup: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)  # all of them make the job `check`
    jobs: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def project_name(root: Path) -> str:
    return _NOT_A_NAME.sub("-", root.resolve().name).strip("-._") or "project"


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(_text(path) or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _node_version(root: Path, package: dict[str, Any]) -> str | None:
    """The first place that says, exact or not. Only an exact version can be pinned."""
    for name in (".nvmrc", ".node-version"):
        said = _text(root / name).strip()
        if said:
            return said
    said = _mapping(package, "volta").get("node") or _mapping(package, "engines").get("node")
    return said if isinstance(said, str) else None


def local_version(tool: str) -> str | None:
    """The exact version of `tool` on this computer, or None."""
    path = shutil.which(tool)
    if path is None:
        return None
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True,
                             timeout=VERSION_TIMEOUT_S, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    match = _EXACT.fullmatch(out)
    return match.group(1) if match else None


def _pin(found: Detected, tool: str, said: str | None) -> None:
    """Pin `said` if exact, else what this computer has, as that is what works here today."""
    exact = _EXACT.fullmatch(said) if said else None
    if exact:
        found.toolchain[tool] = exact.group(1)
        return
    local = local_version(tool)
    project_says = f"the project says {said!r}" if said else "the project does not say"
    if local:
        found.toolchain[tool] = local
        found.notes.append(f"{tool}: pinned {local}, the version on this computer; "
                           f"{project_says}")
    else:
        found.notes.append(f"{tool}: {project_says}, and this computer has none, so nothing "
                           f"is pinned and the machine's own is used")


def _node_manager(root: Path, package: dict[str, Any]) -> tuple[str, str | None]:
    """(package manager, its exact version if the project pins one)."""
    declared = package.get("packageManager")
    match = _PACKAGE_MANAGER.match(declared) if isinstance(declared, str) else None
    if match:
        return match.group(1), match.group(2)
    return next((tool for lock, tool in LOCKFILES if (root / lock).is_file()), "npm"), None


def _node(root: Path, found: Detected) -> None:
    package = _json(root / "package.json")
    manager, version = _node_manager(root, package)
    _pin(found, "node", _node_version(root, package))
    if manager == "pnpm":
        _pin(found, "pnpm", version)
    elif manager == "yarn":
        found.notes.append("yarn: mulebox has no yarn toolchain, so the machine must have it")
    if not any((root / lock).is_file() for lock, _ in LOCKFILES):
        found.notes.append("no lockfile found: the install step needs one to be repeatable")
    found.setup.append(INSTALL[manager])
    if manager in CACHE:
        found.needs.append(CACHE[manager])
    scripts = _mapping(package, "scripts")
    usable = {name: value for name, value in scripts.items()
              if isinstance(value, str) and NO_TEST_SCRIPT not in value}
    for script, job in SCRIPTS:
        if script in usable:
            found.jobs.setdefault(job, f"{manager} run {script}")
    if "build" in usable:
        found.jobs.setdefault("build", f"{manager} run build")
    if "check" in usable:
        found.checks.append(f"{manager} run check")
        return
    found.checks.extend(f"{manager} run {script}" for script, _ in SCRIPTS if script in usable)
    if "build" in usable and "test" not in usable:  # the heavy step should not stay behind
        found.checks.append(f"{manager} run build")


def _python_install(root: Path) -> str | None:
    if (root / "pyproject.toml").is_file():
        try:
            data = tomllib.loads(_text(root / "pyproject.toml"))
        except tomllib.TOMLDecodeError:
            data = {}
        extras = _mapping(_mapping(data, "project"), "optional-dependencies")
        if _mapping(data, "project"):
            return "-e '.[dev]'" if "dev" in extras else "-e ."
    for name in ("requirements-dev.txt", "requirements.txt"):
        if (root / name).is_file():
            return f"-r {name}"
    return None


def _python(root: Path, found: Detected) -> None:
    install = _python_install(root)
    if install is None:
        found.notes.append("python: no [project] table or requirements file, so nothing is "
                           "installed; add the install step to setup")
        return
    found.setup.append("python3 -m venv .venv && "
                       f".venv/bin/pip install -q --disable-pip-version-check {install}")
    found.needs.append(package_cache.PIP)
    found.notes.append("python: the machine's python3 is used, as mulebox has no Python "
                       "toolchain")
    if (root / "tests").is_dir() or (root / "test").is_dir():
        found.jobs.setdefault("test", ".venv/bin/python -m pytest")
        found.checks.append(".venv/bin/python -m pytest")


def _composer(root: Path, found: Detected) -> None:
    composer = _json(root / "composer.json")
    found.setup.append("composer install --no-interaction --prefer-dist")
    found.needs.append(package_cache.COMPOSER)
    dev = _mapping(composer, "require-dev")
    if "test" in _mapping(composer, "scripts"):
        command = "composer test"
    elif "pestphp/pest" in dev:
        command = "vendor/bin/pest"
    elif "phpunit/phpunit" in dev:
        command = "vendor/bin/phpunit"
    else:
        command = None
    if command:
        found.jobs.setdefault("test", command)
        found.checks.append(command)
    found.notes.append("php: the machine must have php and composer, or run them in a "
                       "container with `docker compose exec -T <service> ...`")


def _flutter(root: Path, found: Detected) -> None:
    found.setup.append("flutter pub get")
    found.jobs.setdefault("analyze", "flutter analyze")
    found.checks.append("flutter analyze")
    if (root / "test").is_dir():
        found.jobs.setdefault("test", "flutter test")
        found.checks.append("flutter test")
    found.notes.append("flutter: the machine must have it installed")


def _make_target(root: Path) -> str | None:
    text = _text(root / "Makefile")
    return next((name for name in ("check", "test")
                 if re.search(rf"^{name}\s*:", text, re.MULTILINE)), None)


def _languages(root: Path, found: Detected) -> None:
    if (root / "composer.json").is_file():
        _composer(root, found)
    if (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file():
        _python(root, found)
    if (root / "package.json").is_file():
        _node(root, found)
    if (root / "pubspec.yaml").is_file():
        _flutter(root, found)
    for manifest, command, tool in (("go.mod", "go test ./...", "go"),
                                    ("Cargo.toml", "cargo test", "cargo")):
        if (root / manifest).is_file():
            found.jobs.setdefault("test", command)
            found.checks.append(command)
            found.notes.append(f"{tool}: the machine must have it installed")


def _add_folder(found: Detected, folder: Path) -> None:
    """A part of the project in its own folder: the same, run from that folder."""
    part = Detected(found.project)
    _languages(folder, part)
    name = folder.name
    within = f"cd {shlex.quote(name)} && "
    found.setup.extend(f"({within}{command})" for command in part.setup)
    found.checks.extend(f"({within}{command})" for command in part.checks)
    found.jobs.update({f"{name}-{job}": f"{within}{command}"
                       for job, command in part.jobs.items()})
    found.needs.extend(part.needs)
    found.notes.extend(f"{name}/ {note}" for note in part.notes
                       if note not in found.notes)
    for tool, version in part.toolchain.items():
        found.toolchain.setdefault(tool, version)


def detect(root: Path) -> Detected:
    """What `root` looks like. `checks` is empty when no way to test it could be found."""
    found = Detected(project_name(root))
    found.compose = [name for name in COMPOSE_FILES if (root / name).is_file()][:1]
    if found.compose:
        found.notes.append(f"{found.compose[0]}: its containers start before every job, and "
                           "commands run on the machine; to run one inside a container, use "
                           "`docker compose exec -T <service> ...`")
    _languages(root, found)
    if not found.checks:
        for folder in sorted(path for path in root.iterdir() if path.is_dir()):
            if not folder.name.startswith(".") and folder.name not in NOT_PROJECTS:
                _add_folder(found, folder)
    if not found.checks and (target := _make_target(root)):
        found.checks.append(f"make {target}")
    return found
